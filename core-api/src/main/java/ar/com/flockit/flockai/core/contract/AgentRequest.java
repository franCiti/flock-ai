package ar.com.flockit.flockai.core.contract;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/**
 * A question sent by a client app to a virtual persona. Published to {@code agent.requests}.
 *
 * @param replyTo topic where the client app reads the replies
 * @param clientContext free data of the client app, returned unchanged in every reply; optional
 */
public record AgentRequest(
        int version,
        UUID requestId,
        String conversationId,
        String personaId,
        String question,
        String replyTo,
        Instant sentAt,
        @JsonInclude(JsonInclude.Include.NON_NULL) Map<String, String> clientContext) {}
