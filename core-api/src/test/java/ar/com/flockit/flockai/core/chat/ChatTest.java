package ar.com.flockit.flockai.core.chat;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.contract.AgentReply;
import ar.com.flockit.flockai.core.contract.AgentRequest;
import ar.com.flockit.flockai.core.contract.Outcome;
import ar.com.flockit.flockai.core.contract.PersonaRef;
import ar.com.flockit.flockai.core.kafka.ContractMessages;
import ar.com.flockit.flockai.core.kafka.ContractPublisher;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import ar.com.flockit.flockai.core.support.KafkaRecords;
import ar.com.flockit.flockai.core.support.TestInfrastructure;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

/**
 * The chat end to end over real HTTP: question to {@code agent.requests}, replies of a simulated
 * agent through {@code agent.replies.core-api} to the SSE stream, and reconnection (plan 6.4).
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Import(TestInfrastructure.class)
class ChatTest {

    private static final Duration WAIT = Duration.ofSeconds(30);

    @LocalServerPort
    private int port;

    @Autowired
    private ContractPublisher publisher;

    @Autowired
    private ContractMessages messages;

    private final HttpClient http = HttpClient.newHttpClient();

    /** An event of the stream. */
    private record Event(String id, String name, String data) {}

    /** A signed-in browser: keeps the session and CSRF cookies as the web app does. */
    private final class Browser {
        private final Map<String, String> cookies = new HashMap<>();

        void signIn() throws Exception {
            send(HttpRequest.newBuilder(uri("/api/auth/me")).GET());
            HttpResponse<String> login = send(HttpRequest.newBuilder(uri("/api/auth/login"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "{\"username\": \"admin\", \"password\": \"test-admin-password\"}")));
            assertThat(login.statusCode()).isEqualTo(204);
            // The CSRF token changes with the login and comes back with the next response.
            assertThat(send(HttpRequest.newBuilder(uri("/api/auth/me")).GET()).statusCode())
                    .isEqualTo(200);
        }

        HttpResponse<String> ask(String conversationId, String question) throws Exception {
            String body = "{\"personaId\": \"ana-garcia\", \"question\": \"" + question + "\"}";
            return send(HttpRequest.newBuilder(uri("/api/conversations/" + conversationId + "/messages"))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body)));
        }

        SseStream open(String conversationId, String lastEventId) throws Exception {
            HttpRequest.Builder request = withCookies(
                            HttpRequest.newBuilder(uri("/api/conversations/" + conversationId + "/stream"))
                                    .header("Accept", "text/event-stream"))
                    .GET();
            if (lastEventId != null) {
                request.header("Last-Event-ID", lastEventId);
            }
            HttpResponse<java.util.stream.Stream<String>> response =
                    http.send(request.build(), HttpResponse.BodyHandlers.ofLines());
            assertThat(response.statusCode()).isEqualTo(200);
            return new SseStream(response.body());
        }

        private HttpResponse<String> send(HttpRequest.Builder request) throws Exception {
            HttpResponse<String> response =
                    http.send(withCookies(request).build(), HttpResponse.BodyHandlers.ofString());
            for (String header : response.headers().allValues("Set-Cookie")) {
                String pair = header.split(";", 2)[0];
                int equals = pair.indexOf('=');
                String name = pair.substring(0, equals);
                String value = pair.substring(equals + 1);
                if (value.isEmpty()) {
                    cookies.remove(name);
                } else {
                    cookies.put(name, value);
                }
            }
            return response;
        }

        private HttpRequest.Builder withCookies(HttpRequest.Builder request) {
            if (!cookies.isEmpty()) {
                List<String> pairs = new ArrayList<>();
                cookies.forEach((name, value) -> pairs.add(name + "=" + value));
                request.header("Cookie", String.join("; ", pairs));
            }
            String csrf = cookies.get("XSRF-TOKEN");
            if (csrf != null) {
                request.header("X-XSRF-TOKEN", csrf);
            }
            return request;
        }
    }

    /** An open SSE stream, read by a background thread. */
    private static final class SseStream implements AutoCloseable {
        private final java.util.stream.Stream<String> lines;
        private final BlockingQueue<Event> events = new LinkedBlockingQueue<>();

        SseStream(java.util.stream.Stream<String> lines) {
            this.lines = lines;
            Thread reader = new Thread(this::read, "sse-reader");
            reader.setDaemon(true);
            reader.start();
        }

        Event next() throws InterruptedException {
            Event event = events.poll(WAIT.toMillis(), TimeUnit.MILLISECONDS);
            assertThat(event).as("an event of the stream").isNotNull();
            return event;
        }

        @Override
        public void close() {
            lines.close();
        }

        private void read() {
            String id = null;
            String name = null;
            StringBuilder data = new StringBuilder();
            try {
                Iterator<String> iterator = lines.iterator();
                while (iterator.hasNext()) {
                    String line = iterator.next();
                    if (line.isEmpty()) {
                        if (name != null) {
                            events.add(new Event(id, name, data.toString()));
                        }
                        id = null;
                        name = null;
                        data.setLength(0);
                    } else if (line.startsWith("id:")) {
                        id = line.substring(3).strip();
                    } else if (line.startsWith("event:")) {
                        name = line.substring(6).strip();
                    } else if (line.startsWith("data:")) {
                        data.append(line.substring(5).strip());
                    }
                }
            } catch (UncheckedIOException closed) {
                // The test closed the stream.
            }
        }
    }

    @Test
    void withoutASessionTheChatAnswers401() throws Exception {
        HttpResponse<String> response = http.send(
                HttpRequest.newBuilder(uri("/api/conversations/c-1/stream"))
                        .GET()
                        .build(),
                HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(401);
    }

    @Test
    void theQuestionGoesToTheAgentAndItsRepliesArriveThroughTheStream() throws Exception {
        Browser browser = new Browser();
        browser.signIn();
        String conversationId = "conversation-" + UUID.randomUUID();

        try (SseStream stream = browser.open(conversationId, null)) {
            HttpResponse<String> sent = browser.ask(conversationId, "How do we deploy?");
            assertThat(sent.statusCode()).isEqualTo(202);

            AgentRequest request = agentReceives(conversationId);
            assertThat(sent.body()).contains(request.requestId().toString());
            assertThat(request.personaId()).isEqualTo("ana-garcia");
            assertThat(request.question()).isEqualTo("How do we deploy?");
            assertThat(request.replyTo()).isEqualTo(KafkaTopics.AGENT_REPLIES);

            reply(accepted(request));
            reply(token(request, 1, "We deploy "));
            reply(finalReply(request, 2, "We deploy with the pipeline."));

            Event accepted = stream.next();
            assertThat(accepted.name()).isEqualTo("accepted");
            assertThat(accepted.id()).isEqualTo(request.requestId() + ":0");
            Event token = stream.next();
            assertThat(token.name()).isEqualTo("token");
            assertThat(messages.read(token.data(), AgentReply.class))
                    .isInstanceOfSatisfying(
                            AgentReply.TokenReply.class,
                            reply -> assertThat(reply.text()).isEqualTo("We deploy "));
            Event answer = stream.next();
            assertThat(answer.name()).isEqualTo("final");
            assertThat(answer.data()).contains("We deploy with the pipeline.");
        }
    }

    @Test
    void aReconnectedStreamGetsWhatItMissed() throws Exception {
        Browser browser = new Browser();
        browser.signIn();
        String conversationId = "conversation-" + UUID.randomUUID();

        try (SseStream otherTab = browser.open(conversationId, null)) {
            Event lastSeen;
            AgentRequest request;
            try (SseStream stream = browser.open(conversationId, null)) {
                assertThat(browser.ask(conversationId, "How do we deploy?").statusCode())
                        .isEqualTo(202);
                request = agentReceives(conversationId);
                reply(accepted(request));
                reply(token(request, 1, "We deploy "));
                assertThat(stream.next().name()).isEqualTo("accepted");
                lastSeen = stream.next();
                assertThat(lastSeen.name()).isEqualTo("token");
            }

            // The connection dropped; the agent goes on.
            reply(token(request, 2, "with the pipeline."));
            reply(finalReply(request, 3, "We deploy with the pipeline."));
            for (int seen = 0; seen < 4; seen++) {
                otherTab.next(); // the replies reached the Core API
            }

            try (SseStream reconnected = browser.open(conversationId, lastSeen.id())) {
                Event missedToken = reconnected.next();
                assertThat(missedToken.id()).isEqualTo(request.requestId() + ":2");
                assertThat(missedToken.data()).contains("with the pipeline.");
                Event answer = reconnected.next();
                assertThat(answer.name()).isEqualTo("final");
                assertThat(answer.id()).isEqualTo(request.requestId() + ":3");
            }
        }
    }

    @Test
    void repliesOfAnEarlierRequestAreNotSent() throws Exception {
        Browser browser = new Browser();
        browser.signIn();
        String conversationId = "conversation-" + UUID.randomUUID();

        try (SseStream stream = browser.open(conversationId, null)) {
            browser.ask(conversationId, "First question");
            AgentRequest first = agentReceives(conversationId);
            browser.ask(conversationId, "Second question");
            AgentRequest second = agentReceivesOtherThan(conversationId, first.requestId());

            reply(accepted(first));
            reply(accepted(second));

            Event event = stream.next();
            assertThat(event.id()).isEqualTo(second.requestId() + ":0");
        }
    }

    private AgentRequest agentReceives(String conversationId) {
        return KafkaRecords.find(
                KafkaTopics.AGENT_REQUESTS, conversationId, json -> messages.read(json, AgentRequest.class));
    }

    private AgentRequest agentReceivesOtherThan(String conversationId, UUID requestId) {
        long deadline = System.nanoTime() + WAIT.toNanos();
        while (System.nanoTime() < deadline) {
            List<AgentRequest> requests = KafkaRecords.findAll(
                    KafkaTopics.AGENT_REQUESTS, conversationId, json -> messages.read(json, AgentRequest.class));
            for (AgentRequest request : requests) {
                if (!request.requestId().equals(requestId)) {
                    return request;
                }
            }
        }
        throw new AssertionError("no second request in " + KafkaTopics.AGENT_REQUESTS);
    }

    private void reply(AgentReply reply) throws Exception {
        publisher
                .publish(KafkaTopics.AGENT_REPLIES, reply.conversationId(), reply)
                .get(WAIT.toSeconds(), TimeUnit.SECONDS);
    }

    private static AgentReply accepted(AgentRequest request) {
        return new AgentReply.AcceptedReply(
                1,
                request.requestId(),
                request.conversationId(),
                request.personaId(),
                0,
                Instant.now(),
                null,
                Instant.now().plusSeconds(120));
    }

    private static AgentReply token(AgentRequest request, int seq, String text) {
        return new AgentReply.TokenReply(
                1, request.requestId(), request.conversationId(), request.personaId(), seq, Instant.now(), null, text);
    }

    private static AgentReply finalReply(AgentRequest request, int seq, String answer) {
        return new AgentReply.FinalReply(
                1,
                request.requestId(),
                request.conversationId(),
                request.personaId(),
                seq,
                Instant.now(),
                null,
                answer,
                Outcome.ANSWERED,
                new PersonaRef(request.personaId(), "Ana García"),
                List.of(),
                null,
                new AgentReply.Timing(10, 20));
    }

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }
}
