package ar.com.flockit.flockai.core.ingestion;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

import ar.com.flockit.flockai.core.contract.IngestionEvent;
import ar.com.flockit.flockai.core.contract.IngestionJob;
import ar.com.flockit.flockai.core.kafka.ContractMessages;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import ar.com.flockit.flockai.core.support.IntegrationTest;
import ar.com.flockit.flockai.core.support.KafkaRecords;
import java.time.Instant;
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

/** Manual updates and their history (spec HU4.5, HU4.8, plan 6.3). */
@IntegrationTest
@AutoConfigureMockMvc
class IngestionRunsTest {

    @Autowired
    private MockMvcTester mvc;

    @Autowired
    private IngestionEventsListener events;

    @Autowired
    private ContractMessages messages;

    @Autowired
    private JsonMapper mapper;

    @Test
    @WithMockUser
    void aManualUpdateIsPublishedAndShowsInTheHistory() {
        MvcTestResult response =
                mvc.post().uri("/api/ingestion/runs").with(csrf()).exchange();
        assertThat(response).hasStatus(HttpStatus.ACCEPTED);
        UUID jobId = UUID.fromString(json(response).get("jobId").asString());

        IngestionJob job = KafkaRecords.find(
                KafkaTopics.INGESTION_JOBS, jobId.toString(), json -> messages.read(json, IngestionJob.class));
        assertThat(job.trigger()).isEqualTo(IngestionJob.Trigger.MANUAL);
        assertThat(job.sources()).isEmpty();
        assertThat(run(jobId).get("status").asString()).isEqualTo("requested");
        assertThat(run(jobId).get("trigger").asString()).isEqualTo("manual");

        // The Ingestion Worker answers: the history shows the result.
        Instant at = Instant.now();
        events.apply(new IngestionEvent.StartedEvent(1, jobId, at));
        events.apply(new IngestionEvent.PersonaCompletedEvent(
                1,
                jobId,
                at,
                new IngestionEvent.PersonaSummary(
                        "juan-plataforma",
                        "Juan Pérez",
                        2,
                        1,
                        0,
                        9,
                        4,
                        List.of(new IngestionEvent.SkippedFile("scan.pdf", "no extractable text")),
                        List.of())));
        events.apply(
                new IngestionEvent.CompletedEvent(1, jobId, at, new IngestionEvent.Totals(1, 2, 1, 0, 9, 1, 4, 0)));

        JsonNode run = run(jobId);
        assertThat(run.get("status").asString()).isEqualTo("completed");
        assertThat(run.get("totals").get("secretsMasked").asInt()).isEqualTo(4);
        assertThat(run.get("personas").get(0).get("displayName").asString()).isEqualTo("Juan Pérez");
        assertThat(run.get("personas").get(0).get("skipped").get(0).get("path").asString())
                .isEqualTo("scan.pdf");
        assertThat(run.get("requestedAt").isNull()).isFalse();
    }

    @Test
    @WithMockUser
    void theHistoryIsNewestFirstAndLimited() {
        UUID older = requested();
        UUID newer = requested();
        JsonNode history = json(mvc.get().uri("/api/ingestion/runs?limit=2").exchange());
        assertThat(history).hasSize(2);
        assertThat(history.get(0).get("jobId").asString()).isEqualTo(newer.toString());
        assertThat(history.get(1).get("jobId").asString()).isEqualTo(older.toString());
        assertThat(mvc.get().uri("/api/ingestion/runs?limit=500")).hasStatus(HttpStatus.BAD_REQUEST);
    }

    @Test
    void withoutASessionNothingIsRequested() {
        assertThat(mvc.post().uri("/api/ingestion/runs").with(csrf())).hasStatus(HttpStatus.UNAUTHORIZED);
        assertThat(mvc.get().uri("/api/ingestion/runs")).hasStatus(HttpStatus.UNAUTHORIZED);
    }

    @Test
    @WithMockUser
    void aRequestWithoutTheCsrfTokenIsRejected() {
        assertThat(mvc.post().uri("/api/ingestion/runs")).hasStatus(HttpStatus.FORBIDDEN);
    }

    private UUID requested() {
        MvcTestResult response =
                mvc.post().uri("/api/ingestion/runs").with(csrf()).exchange();
        return UUID.fromString(json(response).get("jobId").asString());
    }

    private JsonNode run(UUID jobId) {
        for (JsonNode run : json(mvc.get().uri("/api/ingestion/runs?limit=100").exchange())) {
            if (run.get("jobId").asString().equals(jobId.toString())) {
                return run;
            }
        }
        throw new AssertionError("run not in the history: " + jobId);
    }

    private JsonNode json(MvcTestResult result) {
        return mapper.readTree(result.getResponse().getContentAsByteArray());
    }
}
