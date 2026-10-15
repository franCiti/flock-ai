package ar.com.flockit.flockai.core.chat;

import ar.com.flockit.flockai.core.contract.AgentReply;
import ar.com.flockit.flockai.core.kafka.ContractMessages;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;

/** Forwards the replies of {@code agent.replies.core-api} to the streams of their conversation. */
@Component
public class AgentRepliesListener {

    private static final Logger LOG = LoggerFactory.getLogger(AgentRepliesListener.class);

    private final ContractMessages messages;
    private final ConversationStreams streams;

    public AgentRepliesListener(ContractMessages messages, ConversationStreams streams) {
        this.messages = messages;
        this.streams = streams;
    }

    @KafkaListener(topics = KafkaTopics.AGENT_REPLIES)
    public void onMessage(String json) {
        AgentReply reply;
        try {
            reply = messages.read(json, AgentReply.class);
        } catch (JacksonException error) {
            LOG.error("Unreadable message in {} skipped: {}", KafkaTopics.AGENT_REPLIES, error.getMessage());
            return;
        }
        // Forwarded as received: the web app reads the contract message itself.
        streams.replyReceived(reply, json);
    }
}
