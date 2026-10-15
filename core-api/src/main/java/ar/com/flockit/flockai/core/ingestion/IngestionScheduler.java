package ar.com.flockit.flockai.core.ingestion;

import ar.com.flockit.flockai.core.contract.IngestionJob;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBooleanProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Asks for a knowledge update every INGESTION_INTERVAL (spec HU4.8, D31). The first one runs one
 * interval after start-up. Disabled with {@code flock.ingestion.scheduler.enabled=false}.
 */
@Component
@ConditionalOnBooleanProperty(name = "flock.ingestion.scheduler.enabled", matchIfMissing = true)
public class IngestionScheduler {

    private static final Logger LOG = LoggerFactory.getLogger(IngestionScheduler.class);

    private final IngestionService ingestion;

    public IngestionScheduler(IngestionService ingestion) {
        this.ingestion = ingestion;
    }

    @Scheduled(initialDelayString = "${flock.ingestion.interval}", fixedDelayString = "${flock.ingestion.interval}")
    public void requestUpdate() {
        try {
            LOG.info("Scheduled knowledge update requested: {}", ingestion.request(IngestionJob.Trigger.SCHEDULED));
        } catch (IngestionService.IngestionUnavailableException error) {
            // The next interval tries again.
            LOG.warn(
                    "Scheduled knowledge update not requested: {}",
                    error.getCause().getMessage());
        }
    }
}
