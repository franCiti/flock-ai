package ar.com.flockit.flockai.core.ingestion;

import ar.com.flockit.flockai.core.contract.IngestionJob;
import ar.com.flockit.flockai.core.kafka.ContractPublisher;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.springframework.stereotype.Service;

/** Asks the Ingestion Worker for a knowledge update (D31, plan 6.5). */
@Service
public class IngestionService {

    private static final Duration PUBLISH_TIMEOUT = Duration.ofSeconds(10);

    private final ContractPublisher publisher;
    private final IngestionRunRepository runs;
    private final Clock clock;

    public IngestionService(ContractPublisher publisher, IngestionRunRepository runs, Clock clock) {
        this.publisher = publisher;
        this.runs = runs;
        this.clock = clock;
    }

    /**
     * Publishes a job to {@code ingestion.jobs}; the run is recorded as requested right away.
     *
     * @throws IngestionUnavailableException if Kafka did not take the job (the run is marked failed)
     */
    public UUID request(IngestionJob.Trigger trigger) {
        UUID jobId = UUID.randomUUID();
        Instant now = clock.instant();
        // TODO(T47): the external sources of the table "source" (stage 3); the folders are always read.
        IngestionJob job = new IngestionJob(1, jobId, trigger, now, List.of());
        runs.requested(jobId, trigger.name().toLowerCase(Locale.ROOT), now);
        try {
            publisher
                    .publish(KafkaTopics.INGESTION_JOBS, jobId.toString(), job)
                    .get(PUBLISH_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw unavailable(jobId, error);
        } catch (ExecutionException | TimeoutException error) {
            throw unavailable(jobId, error);
        }
        return jobId;
    }

    private IngestionUnavailableException unavailable(UUID jobId, Exception error) {
        runs.finished(jobId, "failed", null, "the job could not be published: " + error.getMessage(), clock.instant());
        return new IngestionUnavailableException(error);
    }

    /** Kafka did not accept the job. */
    public static final class IngestionUnavailableException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        IngestionUnavailableException(Throwable cause) {
            super("the knowledge update could not be requested", cause);
        }
    }
}
