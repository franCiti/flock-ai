package ar.com.flockit.flockai.core.chat;

import ar.com.flockit.flockai.core.contract.AgentReply;
import java.io.IOException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.SmartLifecycle;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * The SSE streams of the conversations and the replies of their request in progress (plan 6.4).
 *
 * <p>Each event of the stream is a reply of the agent, with id {@code <requestId>:<seq>}. The replies
 * of the request in progress of each conversation are kept in memory until the answer timeout has
 * passed: a browser that reconnects with {@code Last-Event-ID} gets what it missed. Replaying the
 * buffer and sending new replies happen under the same lock, so nothing is lost or sent twice.
 * One Core API instance in the MVP: the buffers are local.
 *
 * <p>On shutdown the streams are ended first, so the graceful shutdown of the web server does not
 * wait for them; the browsers reconnect to the next instance.
 */
@Component
public class ConversationStreams implements SmartLifecycle {

    private static final Logger LOG = LoggerFactory.getLogger(ConversationStreams.class);

    /** The browser reconnects by itself when the stream ends (EventSource). */
    private static final Duration STREAM_TIMEOUT = Duration.ofMinutes(30);

    /** Margin after the answer timeout before the replies of a request are forgotten. */
    private static final Duration RETENTION_MARGIN = Duration.ofMinutes(1);

    private record Event(String id, UUID requestId, int seq, String name, String data) {}

    private static final class Conversation {
        private UUID requestId;
        private final List<Event> events = new ArrayList<>();
        private final List<SseEmitter> emitters = new CopyOnWriteArrayList<>();
        private Instant expiresAt;
    }

    private final Map<String, Conversation> conversations = new ConcurrentHashMap<>();
    private final Duration retention;
    private final Clock clock;
    private volatile boolean running;

    public ConversationStreams(@Value("${flock.chat.answer-timeout}") Duration answerTimeout, Clock clock) {
        this.retention = answerTimeout.plus(RETENTION_MARGIN);
        this.clock = clock;
    }

    /** A question was sent: its replies replace those of the previous request of the conversation. */
    public void requestSent(String conversationId, UUID requestId) {
        Conversation conversation = conversations.computeIfAbsent(conversationId, id -> new Conversation());
        synchronized (conversation) {
            conversation.requestId = requestId;
            conversation.events.clear();
            conversation.expiresAt = clock.instant().plus(retention);
        }
    }

    /** A reply of the agent: kept and sent to the open streams of its conversation. */
    public void replyReceived(AgentReply reply, String json) {
        Conversation conversation = reply.conversationId() == null ? null : conversations.get(reply.conversationId());
        if (conversation == null) {
            LOG.debug("Reply for an unknown conversation ignored: {}", reply.requestId());
            return;
        }
        synchronized (conversation) {
            if (reply.requestId() == null || !reply.requestId().equals(conversation.requestId)) {
                return; // a reply of an earlier request of the conversation
            }
            boolean repeated = conversation.events.stream().anyMatch(event -> event.seq() == reply.seq());
            if (repeated) {
                return; // delivered again by Kafka
            }
            Event event = new Event(
                    reply.requestId() + ":" + reply.seq(), reply.requestId(), reply.seq(), typeOf(reply), json);
            conversation.events.add(event);
            for (SseEmitter emitter : conversation.emitters) {
                send(conversation, emitter, event);
            }
        }
    }

    /**
     * Opens the stream of a conversation and replays the replies the browser has not seen.
     *
     * @param lastEventId the id of the last event the browser got ({@code Last-Event-ID}), or null
     */
    public SseEmitter subscribe(String conversationId, String lastEventId) {
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT.toMillis());
        Conversation conversation = conversations.computeIfAbsent(conversationId, id -> new Conversation());
        Runnable remove = () -> conversation.emitters.remove(emitter);
        emitter.onCompletion(remove);
        emitter.onTimeout(remove);
        emitter.onError(error -> remove.run());
        synchronized (conversation) {
            // Sent at once: it commits the response, so the browser knows the stream is open.
            sendComment(conversation, emitter, "connected");
            for (Event event : conversation.events) {
                if (isAfter(event, lastEventId)) {
                    send(conversation, emitter, event);
                }
            }
            conversation.emitters.add(emitter);
        }
        return emitter;
    }

    /** Forgets the replies of finished requests and the conversations nobody listens to. */
    @Scheduled(fixedDelay = 60_000)
    public void forgetExpired() {
        Instant now = clock.instant();
        conversations.entrySet().removeIf(entry -> {
            Conversation conversation = entry.getValue();
            synchronized (conversation) {
                if (conversation.expiresAt != null && conversation.expiresAt.isBefore(now)) {
                    conversation.events.clear();
                }
                return conversation.events.isEmpty() && conversation.emitters.isEmpty();
            }
        });
    }

    /** A comment every 20 s keeps idle streams open through proxies. */
    @Scheduled(fixedDelay = 20_000)
    public void keepAlive() {
        for (Conversation conversation : conversations.values()) {
            synchronized (conversation) {
                for (SseEmitter emitter : conversation.emitters) {
                    sendComment(conversation, emitter, "keep-alive");
                }
            }
        }
    }

    @Override
    public void start() {
        running = true;
    }

    @Override
    public void stop() {
        running = false;
        for (Conversation conversation : conversations.values()) {
            synchronized (conversation) {
                conversation.emitters.forEach(SseEmitter::complete);
                conversation.emitters.clear();
            }
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    /** Stopped before the web server, whose graceful shutdown would otherwise wait for the streams. */
    @Override
    public int getPhase() {
        return Integer.MAX_VALUE;
    }

    private static boolean isAfter(Event event, String lastEventId) {
        if (lastEventId == null || lastEventId.isBlank()) {
            return true;
        }
        int separator = lastEventId.lastIndexOf(':');
        if (separator < 0
                || !lastEventId.substring(0, separator).equals(event.requestId().toString())) {
            return true; // the browser saw another request: the whole current one is new to it
        }
        try {
            return event.seq() > Integer.parseInt(lastEventId.substring(separator + 1));
        } catch (NumberFormatException error) {
            return true;
        }
    }

    private static void send(Conversation conversation, SseEmitter emitter, Event event) {
        try {
            emitter.send(SseEmitter.event().id(event.id()).name(event.name()).data(event.data()));
        } catch (IOException | IllegalStateException error) {
            // The browser went away; EventSource reconnects and gets the rest from the buffer.
            conversation.emitters.remove(emitter);
        }
    }

    private static void sendComment(Conversation conversation, SseEmitter emitter, String comment) {
        try {
            emitter.send(SseEmitter.event().comment(comment));
        } catch (IOException | IllegalStateException error) {
            conversation.emitters.remove(emitter);
        }
    }

    private static String typeOf(AgentReply reply) {
        return switch (reply) {
            case AgentReply.AcceptedReply accepted -> "accepted";
            case AgentReply.TokenReply token -> "token";
            case AgentReply.FinalReply finalReply -> "final";
            case AgentReply.ErrorReply error -> "error";
        };
    }
}
