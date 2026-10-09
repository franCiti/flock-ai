package ar.com.flockit.flockai.core.contract;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** Progress and result of an {@link IngestionJob} (internal). Published to {@code ingestion.events}. */
@JsonTypeInfo(use = JsonTypeInfo.Id.NAME, property = "type")
@JsonSubTypes({
    @JsonSubTypes.Type(value = IngestionEvent.StartedEvent.class, name = "started"),
    @JsonSubTypes.Type(value = IngestionEvent.RejectedEvent.class, name = "rejected"),
    @JsonSubTypes.Type(value = IngestionEvent.PersonaCompletedEvent.class, name = "persona_completed"),
    @JsonSubTypes.Type(value = IngestionEvent.PersonaRemovedEvent.class, name = "persona_removed"),
    @JsonSubTypes.Type(value = IngestionEvent.CompletedEvent.class, name = "completed"),
    @JsonSubTypes.Type(value = IngestionEvent.FailedEvent.class, name = "failed")
})
public sealed interface IngestionEvent
        permits IngestionEvent.StartedEvent,
                IngestionEvent.RejectedEvent,
                IngestionEvent.PersonaCompletedEvent,
                IngestionEvent.PersonaRemovedEvent,
                IngestionEvent.CompletedEvent,
                IngestionEvent.FailedEvent {

    int version();

    UUID jobId();

    Instant sentAt();

    /** The update started. */
    record StartedEvent(int version, UUID jobId, Instant sentAt) implements IngestionEvent {}

    /** Another update was already running. */
    record RejectedEvent(int version, UUID jobId, Instant sentAt, String reason) implements IngestionEvent {}

    /** The knowledge of one persona was updated. */
    record PersonaCompletedEvent(int version, UUID jobId, Instant sentAt, PersonaSummary summary)
            implements IngestionEvent {}

    /** The folder of the persona disappeared; the persona and its knowledge were deleted. */
    record PersonaRemovedEvent(int version, UUID jobId, Instant sentAt, String personaId) implements IngestionEvent {}

    /** The update finished. */
    record CompletedEvent(int version, UUID jobId, Instant sentAt, Totals totals) implements IngestionEvent {}

    /** The update stopped because of an error. */
    record FailedEvent(int version, UUID jobId, Instant sentAt, String reason) implements IngestionEvent {}

    /** What changed in the knowledge of one persona. */
    record PersonaSummary(
            String personaId,
            String displayName,
            int added,
            int modified,
            int deleted,
            int unchanged,
            int secretsMasked,
            List<SkippedFile> skipped,
            List<SourceError> sourceErrors) {}

    /** A file that could not be read, and why. */
    record SkippedFile(String path, String reason) {}

    /** An external source that failed, and why. */
    record SourceError(String sourceId, String reason) {}

    /** What changed in the whole update. */
    record Totals(
            int personas,
            int added,
            int modified,
            int deleted,
            int unchanged,
            int skipped,
            int secretsMasked,
            int sourceErrors) {}
}
