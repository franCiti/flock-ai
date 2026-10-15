package ar.com.flockit.flockai.core;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Map;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509ExtendedTrustManager;
import org.apache.kafka.clients.admin.TopicDescription;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIf;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * The real connections (default profile "mtls") against the Docker Compose stack, with the
 * certificate {@code core-api} (plan 7.1-7.3). Skipped when the stack is not running.
 *
 * <p>It leaves no trace: the Kafka listeners stay stopped (they would consume real messages with the
 * group core-api), it only reads (Flyway applies the same migrations the Core API applies at
 * start-up) and describes topics, without producing or consuming messages.
 */
@SpringBootTest(properties = "spring.kafka.listener.auto-startup=false")
@EnabledIf("stackIsRunning")
class MutualTlsStackTest {

    private static final Path CERTS = Path.of("..", "infra", "certs", "out", "core-api");

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private KafkaAdmin kafkaAdmin;

    @DynamicPropertySource
    static void certificates(DynamicPropertyRegistry registry) {
        registry.add(
                "TLS_CERT_FILE",
                () -> CERTS.resolve("core-api.crt").toAbsolutePath().toString());
        registry.add(
                "TLS_KEY_FILE",
                () -> CERTS.resolve("core-api.key").toAbsolutePath().toString());
        registry.add(
                "TLS_CA_FILE", () -> CERTS.resolve("ca.crt").toAbsolutePath().toString());
    }

    static boolean stackIsRunning() {
        return Files.isRegularFile(CERTS.resolve("core-api.crt")) && listening(5433) && listening(9093);
    }

    @Test
    void postgresAuthenticatesTheCertificateOverTls() {
        assertThat(jdbc.queryForObject("SELECT current_user", String.class)).isEqualTo("core_api");
        Boolean tls = jdbc.queryForObject("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()", Boolean.class);
        assertThat(tls).isTrue();
        assertThat(jdbc.queryForObject("SELECT count(*) FROM core.flyway_schema_history", Integer.class))
                .isPositive();
    }

    @Test
    void kafkaAcceptsTheCertificateAndTheAclsShowItsTopics() throws Exception {
        String issuer = kafkaCertificateIssuer();
        String ca = caSubject();
        // An antivirus that inspects TLS (seen with Avast on Windows) replaces the broker certificate
        // with its own: no mutual TLS is possible from this PC, whatever the code does.
        assumeTrue(
                issuer.equals(ca),
                "the TLS of this PC to localhost:9093 is intercepted (broker certificate issued by " + issuer
                        + "); see docs/notas-entorno.md");
        Map<String, TopicDescription> topics =
                kafkaAdmin.describeTopics(KafkaTopics.AGENT_REQUESTS, KafkaTopics.AGENT_REPLIES);
        assertThat(topics).containsOnlyKeys(KafkaTopics.AGENT_REQUESTS, KafkaTopics.AGENT_REPLIES);
        assertThat(topics.get(KafkaTopics.AGENT_REQUESTS).partitions()).hasSize(6);
    }

    /** Issuer of the certificate Java receives from the Kafka broker, without validating it. */
    private static String kafkaCertificateIssuer() throws Exception {
        TrustManager acceptAll = new X509ExtendedTrustManager() {
            @Override
            public void checkClientTrusted(X509Certificate[] chain, String type) {}

            @Override
            public void checkClientTrusted(X509Certificate[] chain, String type, Socket socket) {}

            @Override
            public void checkClientTrusted(X509Certificate[] chain, String type, SSLEngine engine) {}

            @Override
            public void checkServerTrusted(X509Certificate[] chain, String type) {}

            @Override
            public void checkServerTrusted(X509Certificate[] chain, String type, Socket socket) {}

            @Override
            public void checkServerTrusted(X509Certificate[] chain, String type, SSLEngine engine) {}

            @Override
            public X509Certificate[] getAcceptedIssuers() {
                return new X509Certificate[0];
            }
        };
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, new TrustManager[] {acceptAll}, null);
        try (SSLSocket socket = (SSLSocket) context.getSocketFactory().createSocket("localhost", 9093)) {
            socket.startHandshake();
            X509Certificate broker = (X509Certificate) socket.getSession().getPeerCertificates()[0];
            return broker.getIssuerX500Principal().getName();
        }
    }

    private static String caSubject() throws Exception {
        try (InputStream input = Files.newInputStream(CERTS.resolve("ca.crt"))) {
            X509Certificate ca =
                    (X509Certificate) CertificateFactory.getInstance("X.509").generateCertificate(input);
            return ca.getSubjectX500Principal().getName();
        }
    }

    private static boolean listening(int port) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress("localhost", port), 1000);
            return true;
        } catch (IOException error) {
            return false;
        }
    }
}
