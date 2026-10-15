package ar.com.flockit.flockai.core.support;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistrar;
import org.testcontainers.images.builder.Transferable;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

/**
 * Ephemeral PostgreSQL and Kafka for the integration tests (plan 8.2), shared by every test of the
 * run: started once, the first time a test context needs them.
 *
 * <p>Same images as the Docker Compose stack. PostgreSQL runs the same roles and schemas script
 * ({@code infra/postgres/initdb}), so Flyway and the application connect as {@code core_api} with
 * its real privileges. TLS is not involved: these tests cover logic on tables and messages; mutual
 * TLS is checked against the Compose stack ({@code MutualTlsStackTest}).
 */
@TestConfiguration(proxyBeanMethods = false)
public class TestInfrastructure {

    public static final String TEST_PASSWORD = "test-only";

    private static final Path INIT_SCRIPTS = Path.of("..", "infra", "postgres", "initdb");

    @SuppressWarnings("resource") // closed by Testcontainers when the test JVM ends
    private static final PostgreSQLContainer POSTGRES = postgres();

    @SuppressWarnings("resource") // closed by Testcontainers when the test JVM ends
    private static final KafkaContainer KAFKA = new KafkaContainer("apache/kafka:4.3.1");

    static {
        POSTGRES.start();
        KAFKA.start();
    }

    @Bean
    DynamicPropertyRegistrar testInfrastructureProperties() {
        return registry -> {
            registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
            registry.add("spring.datasource.username", () -> "core_api");
            registry.add("spring.datasource.password", () -> TEST_PASSWORD);
            registry.add("spring.kafka.bootstrap-servers", KAFKA::getBootstrapServers);
        };
    }

    public static String kafkaBootstrapServers() {
        return KAFKA.getBootstrapServers();
    }

    private static PostgreSQLContainer postgres() {
        PostgreSQLContainer container = new PostgreSQLContainer("pgvector/pgvector:0.8.7-pg17")
                .withDatabaseName("flock_ai")
                .withUsername("admin")
                .withPassword(TEST_PASSWORD);
        for (Path script : initScripts()) {
            container.withCopyFileToContainer(
                    MountableFile.forHostPath(script), "/docker-entrypoint-initdb.d/" + script.getFileName());
        }
        // Certificates are not used here: the service roles get a test password.
        container.withCopyToContainer(
                Transferable.of("ALTER ROLE core_api PASSWORD '" + TEST_PASSWORD + "';"),
                "/docker-entrypoint-initdb.d/zz-test-passwords.sql");
        return container;
    }

    private static List<Path> initScripts() {
        try (Stream<Path> files = Files.list(INIT_SCRIPTS)) {
            return files.filter(path -> path.toString().endsWith(".sql"))
                    .sorted()
                    .toList();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }
}
