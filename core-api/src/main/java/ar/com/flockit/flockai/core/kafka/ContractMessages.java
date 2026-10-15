package ar.com.flockit.flockai.core.kafka;

import ar.com.flockit.flockai.core.contract.AgentReply;
import ar.com.flockit.flockai.core.contract.AgentRequest;
import ar.com.flockit.flockai.core.contract.AuditEntry;
import ar.com.flockit.flockai.core.contract.IngestionEvent;
import ar.com.flockit.flockai.core.contract.IngestionJob;
import java.util.Map;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * JSON of the contract messages (plan 2.2): camelCase fields, ISO 8601 dates, and unknown fields
 * ignored when reading, so that new optional fields never break a consumer.
 */
@Component
public class ContractMessages {

    /** Value of the {@code schema} header of each message type (plan 2.2). */
    private static final Map<Class<?>, String> SCHEMAS = Map.of(
            AgentRequest.class, "agent-request.v1",
            AgentReply.class, "agent-reply.v1",
            AuditEntry.class, "audit-entry.v1",
            IngestionJob.class, "ingestion-job.v1",
            IngestionEvent.class, "ingestion-event.v1");

    private final JsonMapper mapper;

    public ContractMessages(JsonMapper mapper) {
        this.mapper = mapper;
    }

    public String write(Object message) {
        return mapper.writeValueAsString(message);
    }

    public <T> T read(String json, Class<T> type) {
        return mapper.readValue(json, type);
    }

    /** Schema name of a contract message; fails for anything that is not one. */
    public String schemaOf(Object message) {
        return SCHEMAS.entrySet().stream()
                .filter(entry -> entry.getKey().isInstance(message))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "not a contract message: " + message.getClass().getName()));
    }
}
