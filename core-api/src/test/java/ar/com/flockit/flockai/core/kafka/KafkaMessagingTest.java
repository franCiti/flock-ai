package ar.com.flockit.flockai.core.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.contract.AgentRequest;
import ar.com.flockit.flockai.core.support.IntegrationTest;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.ConsumerFactory;

/**
 * Publishing and consuming contract messages with the Kafka configuration of the application
 * (plan 2.2, 6.5). Each test uses its own topic, created by the broker on first use.
 */
@IntegrationTest
class KafkaMessagingTest {

    @Autowired
    private ContractPublisher publisher;

    @Autowired
    private ContractMessages messages;

    @Autowired
    private ConsumerFactory<String, String> consumers;

    @Test
    void aContractMessageIsPublishedAndConsumedWithItsHeaders() throws Exception {
        String topic = "agent.requests.test-" + UUID.randomUUID();
        AgentRequest request = new AgentRequest(
                1,
                UUID.randomUUID(),
                "web-session-42",
                "juan-plataforma",
                "¿Cómo hago rollback de un deploy?",
                KafkaTopics.AGENT_REPLIES,
                Instant.parse("2026-10-15T12:00:00Z"),
                Map.of("uiMessageId", "m-17"));

        publisher.publish(topic, request.conversationId(), request).get(30, TimeUnit.SECONDS);

        ConsumerRecord<String, String> record = consumeOne(topic);
        assertThat(record.key()).isEqualTo("web-session-42");
        assertThat(header(record, ContractPublisher.CONTENT_TYPE_HEADER)).isEqualTo("application/json");
        assertThat(header(record, ContractPublisher.SCHEMA_HEADER)).isEqualTo("agent-request.v1");
        assertThat(messages.read(record.value(), AgentRequest.class)).isEqualTo(request);
        assertThat(record.value()).contains("\"requestId\"", "\"sentAt\":\"2026-10-15T12:00:00Z\"");
    }

    @Test
    void unknownFieldsAreIgnoredWhenReading() {
        String json = """
                {"version": 1, "requestId": "6f1c2a4e-1b7d-4c0e-9a51-3c2f8d9e0a11",
                 "conversationId": "c1", "personaId": "ana-datos", "question": "Hola",
                 "replyTo": "agent.replies.core-api", "sentAt": "2026-10-15T12:00:00Z",
                 "aFieldOfAFutureVersion": true}
                """;
        assertThat(messages.read(json, AgentRequest.class).personaId()).isEqualTo("ana-datos");
    }

    private ConsumerRecord<String, String> consumeOne(String topic) {
        try (Consumer<String, String> consumer = consumers.createConsumer("core-api-test-" + topic, null)) {
            consumer.subscribe(List.of(topic));
            long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
            while (System.nanoTime() < deadline) {
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));
                if (!records.isEmpty()) {
                    return records.iterator().next();
                }
            }
        }
        throw new AssertionError("no message in " + topic);
    }

    private static String header(ConsumerRecord<String, String> record, String name) {
        return new String(record.headers().lastHeader(name).value(), StandardCharsets.UTF_8);
    }
}
