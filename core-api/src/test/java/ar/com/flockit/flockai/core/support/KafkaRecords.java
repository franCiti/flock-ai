package ar.com.flockit.flockai.core.support;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

/** Reads the test Kafka with a throwaway consumer group, so the application's offsets never move. */
public final class KafkaRecords {

    private KafkaRecords() {}

    /** The value of the first message of {@code topic} with this key, read with {@code reader}. */
    public static <T> T find(String topic, String key, Function<String, T> reader) {
        try (KafkaConsumer<String, String> consumer = consumer()) {
            consumer.subscribe(List.of(topic));
            long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
            while (System.nanoTime() < deadline) {
                for (ConsumerRecord<String, String> record : consumer.poll(Duration.ofMillis(500))) {
                    if (key.equals(record.key())) {
                        return reader.apply(record.value());
                    }
                }
            }
        }
        throw new AssertionError("no message with key " + key + " in " + topic);
    }

    /** The values of the messages of {@code topic} with this key found in a few seconds of reading. */
    public static <T> List<T> findAll(String topic, String key, Function<String, T> reader) {
        List<T> found = new ArrayList<>();
        try (KafkaConsumer<String, String> consumer = consumer()) {
            consumer.subscribe(List.of(topic));
            long deadline = System.nanoTime() + Duration.ofSeconds(3).toNanos();
            while (System.nanoTime() < deadline) {
                for (ConsumerRecord<String, String> record : consumer.poll(Duration.ofMillis(500))) {
                    if (key.equals(record.key())) {
                        found.add(reader.apply(record.value()));
                    }
                }
            }
        }
        return found;
    }

    private static KafkaConsumer<String, String> consumer() {
        Map<String, Object> config = Map.of(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                TestInfrastructure.kafkaBootstrapServers(),
                ConsumerConfig.GROUP_ID_CONFIG,
                "test-reader-" + UUID.randomUUID(),
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
                "earliest",
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false);
        return new KafkaConsumer<>(config, new StringDeserializer(), new StringDeserializer());
    }
}
