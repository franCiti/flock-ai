package ar.com.flockit.flockai.core.kafka;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

/** Publishes contract messages with the headers every message carries (plan 2.2). */
@Component
public class ContractPublisher {

    public static final String CONTENT_TYPE_HEADER = "content-type";
    public static final String SCHEMA_HEADER = "schema";
    private static final String CONTENT_TYPE = "application/json";

    private final KafkaTemplate<String, String> kafka;
    private final ContractMessages messages;

    public ContractPublisher(KafkaTemplate<String, String> kafka, ContractMessages messages) {
        this.kafka = kafka;
        this.messages = messages;
    }

    /**
     * Sends a message; the future completes when every replica has it (acks=all).
     *
     * @param key key of the message: the conversation of a question, the job of an update (plan 2.2)
     */
    public CompletableFuture<SendResult<String, String>> publish(String topic, String key, Object message) {
        ProducerRecord<String, String> record = new ProducerRecord<>(topic, key, messages.write(message));
        record.headers().add(CONTENT_TYPE_HEADER, CONTENT_TYPE.getBytes(StandardCharsets.UTF_8));
        record.headers().add(SCHEMA_HEADER, messages.schemaOf(message).getBytes(StandardCharsets.UTF_8));
        return kafka.send(record);
    }
}
