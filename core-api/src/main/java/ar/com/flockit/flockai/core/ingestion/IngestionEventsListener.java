package ar.com.flockit.flockai.core.ingestion;

import ar.com.flockit.flockai.core.contract.IngestionEvent;
import ar.com.flockit.flockai.core.kafka.ContractMessages;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import ar.com.flockit.flockai.core.persona.PersonaViewRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;

/**
 * Keeps {@code persona_view} and {@code ingestion_run_view} up to date from {@code ingestion.events}
 * (plan 3.5). Every event is applied with idempotent upserts: processing it twice is harmless.
 */
@Component
public class IngestionEventsListener {

    private static final Logger LOG = LoggerFactory.getLogger(IngestionEventsListener.class);

    private final ContractMessages messages;
    private final IngestionRunRepository runs;
    private final PersonaViewRepository personas;

    public IngestionEventsListener(
            ContractMessages messages, IngestionRunRepository runs, PersonaViewRepository personas) {
        this.messages = messages;
        this.runs = runs;
        this.personas = personas;
    }

    @KafkaListener(topics = KafkaTopics.INGESTION_EVENTS)
    @Transactional
    public void onMessage(String json) {
        IngestionEvent event;
        try {
            event = messages.read(json, IngestionEvent.class);
        } catch (JacksonException error) {
            // A message that cannot be read never will: skip it instead of blocking the partition.
            LOG.error("Unreadable message in {} skipped: {}", KafkaTopics.INGESTION_EVENTS, error.getMessage());
            return;
        }
        apply(event);
    }

    @Transactional
    public void apply(IngestionEvent event) {
        switch (event) {
            case IngestionEvent.StartedEvent started -> runs.started(started.jobId(), started.sentAt());
            case IngestionEvent.PersonaCompletedEvent completed -> {
                IngestionEvent.PersonaSummary summary = completed.summary();
                personas.upsert(summary.personaId(), summary.displayName(), completed.sentAt());
                runs.personaCompleted(
                        completed.jobId(), summary.personaId(), messages.write(summary), completed.sentAt());
            }
            case IngestionEvent.PersonaRemovedEvent removed -> {
                personas.delete(removed.personaId());
                runs.personaRemoved(removed.jobId(), removed.personaId(), removed.sentAt());
            }
            case IngestionEvent.CompletedEvent completed ->
                runs.finished(
                        completed.jobId(), "completed", messages.write(completed.totals()), null, completed.sentAt());
            case IngestionEvent.FailedEvent failed ->
                runs.finished(failed.jobId(), "failed", null, failed.reason(), failed.sentAt());
            case IngestionEvent.RejectedEvent rejected ->
                runs.finished(rejected.jobId(), "rejected", null, rejected.reason(), rejected.sentAt());
        }
    }
}
