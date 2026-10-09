package ar.com.flockit.flockai.core.contract;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * A message of the reply to an {@link AgentRequest}. Published to {@code agent.replies.<clientId>}.
 * Every request ends with exactly one {@link FinalReply} or {@link ErrorReply}.
 */
@JsonTypeInfo(use = JsonTypeInfo.Id.NAME, property = "type")
@JsonSubTypes({
    @JsonSubTypes.Type(value = AgentReply.AcceptedReply.class, name = "accepted"),
    @JsonSubTypes.Type(value = AgentReply.TokenReply.class, name = "token"),
    @JsonSubTypes.Type(value = AgentReply.FinalReply.class, name = "final"),
    @JsonSubTypes.Type(value = AgentReply.ErrorReply.class, name = "error")
})
public sealed interface AgentReply
        permits AgentReply.AcceptedReply, AgentReply.TokenReply, AgentReply.FinalReply, AgentReply.ErrorReply {

    int version();

    /** The request id; null only when the request could not be read. */
    UUID requestId();

    String conversationId();

    String personaId();

    /** Order of the message within the request, starting at 0. */
    int seq();

    Instant sentAt();

    /** The clientContext of the request, unchanged; optional. */
    Map<String, String> clientContext();

    /** The agent took the request; the final reply arrives before {@code deadlineAt}. */
    record AcceptedReply(
            int version,
            UUID requestId,
            String conversationId,
            String personaId,
            int seq,
            Instant sentAt,
            @JsonInclude(JsonInclude.Include.NON_NULL) Map<String, String> clientContext,
            Instant deadlineAt)
            implements AgentReply {}

    /** A fragment of the answer being generated: {@code text} is appended to the answer so far. */
    record TokenReply(
            int version,
            UUID requestId,
            String conversationId,
            String personaId,
            int seq,
            Instant sentAt,
            @JsonInclude(JsonInclude.Include.NON_NULL) Map<String, String> clientContext,
            String text)
            implements AgentReply {}

    /**
     * The complete answer, in Markdown. Its text replaces whatever was built from the tokens.
     *
     * @param referral another persona that can probably help, or null
     */
    record FinalReply(
            int version,
            UUID requestId,
            String conversationId,
            String personaId,
            int seq,
            Instant sentAt,
            @JsonInclude(JsonInclude.Include.NON_NULL) Map<String, String> clientContext,
            String answer,
            Outcome outcome,
            PersonaRef persona,
            List<Citation> citations,
            PersonaRef referral,
            Timing timing)
            implements AgentReply {}

    /**
     * The request ended without an answer.
     *
     * @param retryable whether retrying the same request later makes sense
     */
    record ErrorReply(
            int version,
            UUID requestId,
            String conversationId,
            String personaId,
            int seq,
            Instant sentAt,
            @JsonInclude(JsonInclude.Include.NON_NULL) Map<String, String> clientContext,
            ErrorCode code,
            String message,
            boolean retryable)
            implements AgentReply {}

    /** Durations of a request, in milliseconds; {@code firstTokenMs} is null when no token was sent. */
    record Timing(Integer firstTokenMs, int totalMs) {}
}
