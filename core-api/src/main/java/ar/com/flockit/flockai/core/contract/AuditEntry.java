package ar.com.flockit.flockai.core.contract;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Record of a processed request (internal). Published to {@code agent.audit}. Contains questions and
 * answers: only the Core API may read it.
 */
public record AuditEntry(
        int version,
        UUID auditId,
        UUID requestId,
        String clientId,
        String conversationId,
        String personaId,
        String question,
        String answer,
        AuditOutcome outcome,
        ErrorCode errorCode,
        List<Citation> citations,
        String referralPersonaId,
        List<Flag> flags,
        String llmModel,
        String promptVersion,
        Integer firstTokenMs,
        Integer totalMs,
        Instant createdAt) {

    /** The outcome of the final reply, or {@code ERROR}. */
    public enum AuditOutcome {
        @JsonProperty("answered")
        ANSWERED,
        @JsonProperty("partially_answered")
        PARTIALLY_ANSWERED,
        @JsonProperty("no_information")
        NO_INFORMATION,
        @JsonProperty("out_of_scope")
        OUT_OF_SCOPE,
        @JsonProperty("small_talk")
        SMALL_TALK,
        @JsonProperty("about_assistant")
        ABOUT_ASSISTANT,
        @JsonProperty("error")
        ERROR
    }

    /** Something noteworthy that happened while processing the request. */
    public enum Flag {
        @JsonProperty("injection_suspected")
        INJECTION_SUSPECTED,
        @JsonProperty("rate_limited")
        RATE_LIMITED,
        @JsonProperty("question_too_long")
        QUESTION_TOO_LONG,
        @JsonProperty("invalid_request")
        INVALID_REQUEST
    }
}
