package ar.com.flockit.flockai.core;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.audit.AuditViewRepository;
import ar.com.flockit.flockai.core.contract.AuditEntry;
import ar.com.flockit.flockai.core.contract.Citation;
import ar.com.flockit.flockai.core.contract.ErrorCode;
import ar.com.flockit.flockai.core.contract.IngestionEvent;
import ar.com.flockit.flockai.core.contract.SourceType;
import ar.com.flockit.flockai.core.ingestion.IngestionEventsListener;
import ar.com.flockit.flockai.core.kafka.ContractPublisher;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import ar.com.flockit.flockai.core.support.IntegrationTest;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.kafka.core.KafkaTemplate;

/** Read copies filled from Kafka: inserts, updates, deletes and idempotency (plan 3.5, T33). */
@IntegrationTest
class ReadCopiesTest {

    private static final Instant T0 = Instant.parse("2026-10-15T03:00:00Z");

    @Autowired
    private IngestionEventsListener ingestion;

    @Autowired
    private AuditViewRepository audit;

    @Autowired
    private ContractPublisher publisher;

    @Autowired
    private KafkaTemplate<String, String> kafka;

    @Autowired
    private JdbcClient jdbc;

    // --- ingestion.events -> persona_view and ingestion_run_view -------------------------------------

    @Test
    void aWholeUpdateIsCopiedAndApplyingItTwiceChangesNothing() {
        UUID job = UUID.randomUUID();
        String persona = "juan-" + job.toString().substring(0, 8);
        List<IngestionEvent> events = List.of(
                new IngestionEvent.StartedEvent(1, job, T0),
                completed(job, persona, "Juan Pérez", 3, T0.plusSeconds(10)),
                new IngestionEvent.CompletedEvent(1, job, T0.plusSeconds(20), totals(3)));

        events.forEach(ingestion::apply);
        Map<String, Object> first = run(job);
        events.forEach(ingestion::apply);

        assertThat(run(job)).isEqualTo(first);
        assertThat(first)
                .containsEntry("status", "completed")
                .containsEntry("removed_personas", "[]")
                .containsEntry("reason", null);
        assertThat((String) first.get("personas")).contains("\"" + persona + "\"", "\"added\": 3");
        assertThat((String) first.get("totals")).contains("\"added\": 3");
        assertThat(displayName(persona)).isEqualTo("Juan Pérez");
    }

    @Test
    void aPersonaIsUpdatedAndThenRemoved() {
        UUID first = UUID.randomUUID();
        UUID second = UUID.randomUUID();
        String persona = "ana-" + first.toString().substring(0, 8);

        ingestion.apply(completed(first, persona, "Ana", 1, T0));
        ingestion.apply(completed(second, persona, "Ana Gómez", 1, T0.plusSeconds(60)));
        assertThat(displayName(persona)).isEqualTo("Ana Gómez");

        // An older message arriving late does not undo the newer name.
        ingestion.apply(completed(first, persona, "Ana", 1, T0));
        assertThat(displayName(persona)).isEqualTo("Ana Gómez");

        UUID third = UUID.randomUUID();
        ingestion.apply(new IngestionEvent.PersonaRemovedEvent(1, third, T0.plusSeconds(120), persona));
        ingestion.apply(new IngestionEvent.PersonaRemovedEvent(1, third, T0.plusSeconds(120), persona));
        assertThat(displayName(persona)).isNull();
        assertThat(run(third)).containsEntry("removed_personas", "[\"" + persona + "\"]");
    }

    @Test
    void aRepeatedStartDoesNotReopenAFinishedRun() {
        UUID job = UUID.randomUUID();
        ingestion.apply(new IngestionEvent.StartedEvent(1, job, T0));
        ingestion.apply(new IngestionEvent.FailedEvent(1, job, T0.plusSeconds(5), "disk full"));
        ingestion.apply(new IngestionEvent.StartedEvent(1, job, T0));
        assertThat(run(job)).containsEntry("status", "failed").containsEntry("reason", "disk full");
    }

    @Test
    void aRejectedUpdateKeepsItsReason() {
        UUID job = UUID.randomUUID();
        ingestion.apply(new IngestionEvent.RejectedEvent(1, job, T0, "another update is running"));
        assertThat(run(job)).containsEntry("status", "rejected").containsEntry("reason", "another update is running");
    }

    // --- agent.audit -> audit_entry_view --------------------------------------------------------------

    @Test
    void anAuditEntryIsCopiedOnce() {
        AuditEntry entry = auditEntry(UUID.randomUUID());
        audit.save(entry);
        audit.save(entry);

        Map<String, Object> row =
                jdbc.sql("""
                        SELECT outcome, error_code, flags::text AS flags, citations::text AS citations,
                               persona_id, first_token_ms, (SELECT count(*) FROM audit_entry_view WHERE id = :id) AS copies
                        FROM audit_entry_view WHERE id = :id""").param("id", entry.auditId()).query().singleRow();
        assertThat(row)
                .containsEntry("outcome", "error")
                .containsEntry("error_code", "RATE_LIMITED")
                .containsEntry("flags", "{rate_limited}")
                .containsEntry("persona_id", "juan-plataforma")
                .containsEntry("first_token_ms", null)
                .containsEntry("copies", 1L);
        assertThat((String) row.get("citations")).contains("\"documentId\"", "\"sourceType\": \"file\"");
    }

    // --- The listeners, over Kafka ------------------------------------------------------------------

    @Test
    void theListenersFillTheCopiesFromKafkaAndSkipUnreadableMessages() throws Exception {
        UUID job = UUID.randomUUID();
        String persona = "kafka-" + job.toString().substring(0, 8);
        kafka.send(KafkaTopics.INGESTION_EVENTS, job.toString(), "{not json").get(30, TimeUnit.SECONDS);
        publisher
                .publish(KafkaTopics.INGESTION_EVENTS, job.toString(), completed(job, persona, "Por Kafka", 1, T0))
                .get(30, TimeUnit.SECONDS);
        AuditEntry entry = auditEntry(UUID.randomUUID());
        kafka.send(KafkaTopics.AGENT_AUDIT, "x", "{not json").get(30, TimeUnit.SECONDS);
        publisher
                .publish(KafkaTopics.AGENT_AUDIT, entry.requestId().toString(), entry)
                .get(30, TimeUnit.SECONDS);

        assertThat(eventually(() -> displayName(persona))).isEqualTo("Por Kafka");
        assertThat(eventually(() -> jdbc.sql("SELECT count(*) FROM audit_entry_view WHERE id = ?")
                                .param(entry.auditId())
                                .query(Long.class)
                                .single()
                                .equals(1L)
                        ? "copied"
                        : null))
                .isEqualTo("copied");
    }

    // --- Helpers ----------------------------------------------------------------------------------

    private static IngestionEvent.PersonaCompletedEvent completed(
            UUID job, String persona, String displayName, int added, Instant at) {
        return new IngestionEvent.PersonaCompletedEvent(
                1,
                job,
                at,
                new IngestionEvent.PersonaSummary(persona, displayName, added, 0, 0, 5, 0, List.of(), List.of()));
    }

    private static IngestionEvent.Totals totals(int added) {
        return new IngestionEvent.Totals(1, added, 0, 0, 5, 0, 0, 0);
    }

    private static AuditEntry auditEntry(UUID id) {
        return new AuditEntry(
                1,
                id,
                UUID.randomUUID(),
                "core-api",
                "c1",
                "juan-plataforma",
                "¿Cómo hago rollback?",
                null,
                AuditEntry.AuditOutcome.ERROR,
                ErrorCode.RATE_LIMITED,
                List.of(new Citation(
                        "file:juan-plataforma:rollback.md", "rollback", null, "rollback.md", null, SourceType.FILE)),
                null,
                List.of(AuditEntry.Flag.RATE_LIMITED),
                "fake",
                "abc",
                null,
                12,
                T0);
    }

    private Map<String, Object> run(UUID job) {
        return jdbc.sql("""
                        SELECT status, personas::text AS personas, totals::text AS totals,
                               removed_personas::text AS removed_personas, reason
                        FROM ingestion_run_view WHERE job_id = ?""").param(job).query().singleRow();
    }

    private String displayName(String persona) {
        return jdbc.sql("SELECT display_name FROM persona_view WHERE id = ?")
                .param(persona)
                .query(String.class)
                .optional()
                .orElse(null);
    }

    private static <T> T eventually(Supplier<T> value) throws InterruptedException {
        long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        while (System.nanoTime() < deadline) {
            T current = value.get();
            if (current != null) {
                return current;
            }
            Thread.sleep(200);
        }
        return null;
    }
}
