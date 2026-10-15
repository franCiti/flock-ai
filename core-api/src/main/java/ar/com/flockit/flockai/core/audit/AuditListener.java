package ar.com.flockit.flockai.core.audit;

import ar.com.flockit.flockai.core.contract.AuditEntry;
import ar.com.flockit.flockai.core.kafka.ContractMessages;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;

/** Copies {@code agent.audit} into {@code audit_entry_view} (plan 3.5). */
@Component
public class AuditListener {

    private static final Logger LOG = LoggerFactory.getLogger(AuditListener.class);

    private final ContractMessages messages;
    private final AuditViewRepository audit;

    public AuditListener(ContractMessages messages, AuditViewRepository audit) {
        this.messages = messages;
        this.audit = audit;
    }

    @KafkaListener(topics = KafkaTopics.AGENT_AUDIT)
    public void onMessage(String json) {
        AuditEntry entry;
        try {
            entry = messages.read(json, AuditEntry.class);
        } catch (JacksonException error) {
            // A message that cannot be read never will: skip it instead of blocking the partition.
            LOG.error("Unreadable message in {} skipped: {}", KafkaTopics.AGENT_AUDIT, error.getMessage());
            return;
        }
        audit.save(entry);
    }
}
