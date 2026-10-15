package ar.com.flockit.flockai.core.ingestion;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.contract.IngestionJob;
import ar.com.flockit.flockai.core.kafka.ContractMessages;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import ar.com.flockit.flockai.core.support.IntegrationTest;
import ar.com.flockit.flockai.core.support.KafkaRecords;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.TestPropertySource;

/** The scheduler asks for an update every INGESTION_INTERVAL (spec HU4.8, D31). */
@IntegrationTest
@TestPropertySource(properties = {"flock.ingestion.scheduler.enabled=true", "flock.ingestion.interval=1s"})
class IngestionSchedulerTest {

    @Autowired
    private JdbcClient jdbc;

    @Autowired
    private ContractMessages messages;

    @Test
    void scheduledUpdatesArePublishedEveryInterval() throws InterruptedException {
        long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        long scheduled = 0;
        while (scheduled < 2 && System.nanoTime() < deadline) {
            Thread.sleep(500);
            scheduled = jdbc.sql("SELECT count(*) FROM ingestion_run_view WHERE trigger = 'scheduled'")
                    .query(Long.class)
                    .single();
        }
        assertThat(scheduled).isGreaterThanOrEqualTo(2);

        UUID jobId = jdbc.sql("SELECT job_id FROM ingestion_run_view WHERE trigger = 'scheduled' LIMIT 1")
                .query(UUID.class)
                .single();
        IngestionJob job = KafkaRecords.find(
                KafkaTopics.INGESTION_JOBS, jobId.toString(), json -> messages.read(json, IngestionJob.class));
        assertThat(job.trigger()).isEqualTo(IngestionJob.Trigger.SCHEDULED);
    }
}
