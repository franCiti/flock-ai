package ar.com.flockit.flockai.core.audit;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.contract.AuditEntry;
import ar.com.flockit.flockai.core.contract.Citation;
import ar.com.flockit.flockai.core.contract.ErrorCode;
import ar.com.flockit.flockai.core.contract.SourceType;
import ar.com.flockit.flockai.core.support.IntegrationTest;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpStatus;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.assertj.MvcTestResult;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** The audit log for the operator: paging and each filter (spec HU8.2, plan 6.3). */
@IntegrationTest
@AutoConfigureMockMvc
class AuditApiTest {

    private static final Instant T0 = Instant.parse("2026-10-01T12:00:00Z");

    @Autowired
    private MockMvcTester mvc;

    @Autowired
    private AuditViewRepository audit;

    @Autowired
    private JsonMapper mapper;

    /** Each test uses its own persona, so the entries of other tests never get in the way. */
    private final String persona = "persona-" + UUID.randomUUID();

    @Test
    void withoutASessionTheAuditLogAnswers401() {
        assertThat(mvc.get().uri("/api/audit").exchange()).hasStatus(HttpStatus.UNAUTHORIZED);
    }

    @Test
    @WithMockUser
    void entriesComeNewestFirstInPages() {
        UUID oldest = save(entry(T0));
        UUID middle = save(entry(T0.plus(1, ChronoUnit.HOURS)));
        UUID newest = save(entry(T0.plus(2, ChronoUnit.HOURS)));

        JsonNode first = find("personaId=" + persona + "&size=2");
        assertThat(ids(first)).containsExactly(newest, middle);
        assertThat(first.get("totalItems").asLong()).isEqualTo(3);
        assertThat(first.get("page").asInt()).isZero();
        assertThat(first.get("size").asInt()).isEqualTo(2);
        assertThat(ids(find("personaId=" + persona + "&size=2&page=1"))).containsExactly(oldest);
    }

    @Test
    @WithMockUser
    void anEntryShowsWhatTheAgentRecorded() {
        AuditEntry entry = new AuditEntry(
                1,
                UUID.randomUUID(),
                UUID.randomUUID(),
                "core-api",
                "conversation-1",
                persona,
                "How do we deploy?",
                "With the pipeline.",
                AuditEntry.AuditOutcome.PARTIALLY_ANSWERED,
                null,
                List.of(new Citation("doc-1", "Rollback", null, "deploy/rollback.md", "Steps", SourceType.FILE)),
                "luis-datos",
                List.of(AuditEntry.Flag.INJECTION_SUSPECTED),
                "test-model",
                "v1",
                120,
                900,
                T0);
        audit.save(entry);

        JsonNode item = find("personaId=" + persona).get("items").get(0);
        assertThat(item.get("id").asString()).isEqualTo(entry.auditId().toString());
        assertThat(item.get("question").asString()).isEqualTo("How do we deploy?");
        assertThat(item.get("outcome").asString()).isEqualTo("partially_answered");
        assertThat(item.get("flags").get(0).asString()).isEqualTo("injection_suspected");
        assertThat(item.get("citations").get(0).get("path").asString()).isEqualTo("deploy/rollback.md");
        assertThat(item.get("referralPersonaId").asString()).isEqualTo("luis-datos");
        assertThat(item.get("firstTokenMs").asInt()).isEqualTo(120);
        assertThat(item.get("createdAt").asString()).isEqualTo("2026-10-01T12:00:00Z");
    }

    @Test
    @WithMockUser
    void filterByPersona() {
        UUID mine = save(entry(T0));
        String other = "persona-" + UUID.randomUUID();
        AuditEntry theirs = withPersona(entry(T0), other);
        audit.save(theirs);

        assertThat(ids(find("personaId=" + persona))).containsExactly(mine);
        assertThat(ids(find("personaId=" + other))).containsExactly(theirs.auditId());
    }

    @Test
    @WithMockUser
    void filterByDatesIncludesFromAndExcludesTo() {
        save(entry(T0.minus(1, ChronoUnit.DAYS)));
        UUID atFrom = save(entry(T0));
        UUID inside = save(entry(T0.plus(1, ChronoUnit.HOURS)));
        save(entry(T0.plus(1, ChronoUnit.DAYS)));

        JsonNode page = find("personaId=" + persona + "&from=2026-10-01T12:00:00Z&to=2026-10-02T12:00:00Z");
        assertThat(ids(page)).containsExactly(inside, atFrom);
        assertThat(ids(find("personaId=" + persona + "&from=2026-10-02T12:00:00Z")))
                .hasSize(1);
        assertThat(ids(find("personaId=" + persona + "&to=2026-10-01T12:00:00Z")))
                .hasSize(1);
    }

    @Test
    @WithMockUser
    void filterByOutcomeTakesAnyOfSeveral() {
        save(entry(T0));
        UUID noInformation = save(withOutcome(entry(T0.plusSeconds(1)), AuditEntry.AuditOutcome.NO_INFORMATION));
        UUID error = save(withOutcome(entry(T0.plusSeconds(2)), AuditEntry.AuditOutcome.ERROR));

        assertThat(ids(find("personaId=" + persona + "&outcome=no_information")))
                .containsExactly(noInformation);
        assertThat(ids(find("personaId=" + persona + "&outcome=no_information&outcome=error")))
                .containsExactly(error, noInformation);
    }

    @Test
    @WithMockUser
    void filterByFlagTakesAnyOfSeveral() {
        save(entry(T0));
        UUID injection = save(withFlags(entry(T0.plusSeconds(1)), List.of(AuditEntry.Flag.INJECTION_SUSPECTED)));
        UUID rejected = save(withFlags(
                entry(T0.plusSeconds(2)), List.of(AuditEntry.Flag.RATE_LIMITED, AuditEntry.Flag.INVALID_REQUEST)));

        assertThat(ids(find("personaId=" + persona + "&flag=injection_suspected")))
                .containsExactly(injection);
        assertThat(ids(find("personaId=" + persona + "&flag=injection_suspected&flag=invalid_request")))
                .containsExactly(rejected, injection);
    }

    @Test
    @WithMockUser
    void filterByReferral() {
        UUID plain = save(entry(T0));
        UUID referred = save(withReferral(entry(T0.plusSeconds(1)), "luis-datos"));

        assertThat(ids(find("personaId=" + persona + "&referred=true"))).containsExactly(referred);
        assertThat(ids(find("personaId=" + persona + "&referred=false"))).containsExactly(plain);
    }

    @Test
    @WithMockUser
    void theFiltersApplyTogether() {
        save(withOutcome(entry(T0), AuditEntry.AuditOutcome.NO_INFORMATION));
        UUID match = save(withReferral(
                withOutcome(entry(T0.plusSeconds(1)), AuditEntry.AuditOutcome.NO_INFORMATION), "luis-datos"));
        save(withReferral(entry(T0.plusSeconds(2)), "luis-datos"));

        assertThat(ids(find("personaId=" + persona + "&outcome=no_information&referred=true")))
                .containsExactly(match);
    }

    @Test
    @WithMockUser
    void unknownValuesAndPagesOutOfRangeAreRejected() {
        assertThat(mvc.get().uri("/api/audit?outcome=great").exchange()).hasStatus(HttpStatus.BAD_REQUEST);
        assertThat(mvc.get().uri("/api/audit?flag=NOPE").exchange()).hasStatus(HttpStatus.BAD_REQUEST);
        assertThat(mvc.get().uri("/api/audit?size=101").exchange()).hasStatus(HttpStatus.BAD_REQUEST);
        assertThat(mvc.get().uri("/api/audit?page=-1").exchange()).hasStatus(HttpStatus.BAD_REQUEST);
        assertThat(mvc.get().uri("/api/audit?from=yesterday").exchange()).hasStatus(HttpStatus.BAD_REQUEST);
    }

    private JsonNode find(String query) {
        MvcTestResult result = mvc.get().uri("/api/audit?" + query).exchange();
        assertThat(result).hasStatus(HttpStatus.OK);
        return mapper.readTree(result.getResponse().getContentAsByteArray());
    }

    private static List<UUID> ids(JsonNode page) {
        List<UUID> ids = new ArrayList<>();
        page.get("items").forEach(item -> ids.add(UUID.fromString(item.get("id").asString())));
        return ids;
    }

    private UUID save(AuditEntry entry) {
        audit.save(entry);
        return entry.auditId();
    }

    private AuditEntry entry(Instant createdAt) {
        return new AuditEntry(
                1,
                UUID.randomUUID(),
                UUID.randomUUID(),
                "core-api",
                "conversation-1",
                persona,
                "A question",
                "An answer",
                AuditEntry.AuditOutcome.ANSWERED,
                null,
                List.of(),
                null,
                List.of(),
                "test-model",
                "v1",
                100,
                500,
                createdAt);
    }

    private static AuditEntry withPersona(AuditEntry e, String personaId) {
        return new AuditEntry(
                e.version(),
                e.auditId(),
                e.requestId(),
                e.clientId(),
                e.conversationId(),
                personaId,
                e.question(),
                e.answer(),
                e.outcome(),
                e.errorCode(),
                e.citations(),
                e.referralPersonaId(),
                e.flags(),
                e.llmModel(),
                e.promptVersion(),
                e.firstTokenMs(),
                e.totalMs(),
                e.createdAt());
    }

    private static AuditEntry withOutcome(AuditEntry e, AuditEntry.AuditOutcome outcome) {
        ErrorCode errorCode = outcome == AuditEntry.AuditOutcome.ERROR ? ErrorCode.LLM_UNAVAILABLE : null;
        return new AuditEntry(
                e.version(),
                e.auditId(),
                e.requestId(),
                e.clientId(),
                e.conversationId(),
                e.personaId(),
                e.question(),
                e.answer(),
                outcome,
                errorCode,
                e.citations(),
                e.referralPersonaId(),
                e.flags(),
                e.llmModel(),
                e.promptVersion(),
                e.firstTokenMs(),
                e.totalMs(),
                e.createdAt());
    }

    private static AuditEntry withFlags(AuditEntry e, List<AuditEntry.Flag> flags) {
        return new AuditEntry(
                e.version(),
                e.auditId(),
                e.requestId(),
                e.clientId(),
                e.conversationId(),
                e.personaId(),
                e.question(),
                e.answer(),
                e.outcome(),
                e.errorCode(),
                e.citations(),
                e.referralPersonaId(),
                flags,
                e.llmModel(),
                e.promptVersion(),
                e.firstTokenMs(),
                e.totalMs(),
                e.createdAt());
    }

    private static AuditEntry withReferral(AuditEntry e, String referralPersonaId) {
        return new AuditEntry(
                e.version(),
                e.auditId(),
                e.requestId(),
                e.clientId(),
                e.conversationId(),
                e.personaId(),
                e.question(),
                e.answer(),
                e.outcome(),
                e.errorCode(),
                e.citations(),
                referralPersonaId,
                e.flags(),
                e.llmModel(),
                e.promptVersion(),
                e.firstTokenMs(),
                e.totalMs(),
                e.createdAt());
    }
}
