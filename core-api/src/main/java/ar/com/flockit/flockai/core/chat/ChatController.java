package ar.com.flockit.flockai.core.chat;

import ar.com.flockit.flockai.core.contract.AgentRequest;
import ar.com.flockit.flockai.core.kafka.ContractPublisher;
import ar.com.flockit.flockai.core.kafka.KafkaTopics;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Clock;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * The chat of the web app: questions go to the agent over Kafka and its replies come back as
 * Server-Sent Events (spec HU6, HU10, plan 6.4). The web app opens the stream before asking.
 */
@RestController
@RequestMapping("/api/conversations/{conversationId}")
@Tag(name = "chat", description = "Questions to a virtual persona and their streamed replies")
public class ChatController {

    private static final Duration PUBLISH_TIMEOUT = Duration.ofSeconds(10);

    /** A question to a persona. Its maximum length is checked by the agent (GET /api/config). */
    public record Question(
            @NotBlank @Pattern(regexp = "^[a-z0-9][a-z0-9-]{0,62}$") String personaId,

            @NotBlank String question) {}

    /** The request of a question; its replies carry this id. */
    public record SentQuestion(UUID requestId) {}

    private final ContractPublisher publisher;
    private final ConversationStreams streams;
    private final Clock clock;

    public ChatController(ContractPublisher publisher, ConversationStreams streams, Clock clock) {
        this.publisher = publisher;
        this.streams = streams;
        this.clock = clock;
    }

    @PostMapping(value = "/messages", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Ask a question: its replies arrive through the stream of the conversation")
    @ApiResponse(responseCode = "202", description = "Sent to the agent")
    @ApiResponse(
            responseCode = "503",
            description = "Kafka is not available",
            content =
                    @Content(
                            mediaType = "application/problem+json",
                            schema = @Schema(implementation = ProblemDetail.class)))
    public ResponseEntity<SentQuestion> send(
            @PathVariable @Size(min = 1, max = 128) String conversationId, @Valid @RequestBody Question question)
            throws InterruptedException {
        UUID requestId = UUID.randomUUID();
        AgentRequest request = new AgentRequest(
                1,
                requestId,
                conversationId,
                question.personaId(),
                question.question(),
                KafkaTopics.AGENT_REPLIES,
                clock.instant(),
                null);
        streams.requestSent(conversationId, requestId);
        try {
            publisher
                    .publish(KafkaTopics.AGENT_REQUESTS, conversationId, request)
                    .get(PUBLISH_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
        } catch (ExecutionException | TimeoutException error) {
            throw new AgentUnavailableException(error);
        }
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(new SentQuestion(requestId));
    }

    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @Operation(
            summary = "Replies of the conversation (Server-Sent Events)",
            description = "Each event is an AgentReply of the contract (accepted, token, final, error) "
                    + "with id <requestId>:<seq>. Reconnecting with Last-Event-ID replays what was missed "
                    + "of the request in progress.",
            responses =
                    @ApiResponse(
                            responseCode = "200",
                            description = "The stream of events",
                            content = @Content(mediaType = "text/event-stream", schema = @Schema(type = "string"))))
    public SseEmitter stream(
            @PathVariable @Size(min = 1, max = 128) String conversationId,
            @Parameter(description = "Id of the last event received")
                    @RequestHeader(value = "Last-Event-ID", required = false)
                    String lastEventId) {
        return streams.subscribe(conversationId, lastEventId);
    }

    @ExceptionHandler(AgentUnavailableException.class)
    ResponseEntity<ProblemDetail> unavailable(AgentUnavailableException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.SERVICE_UNAVAILABLE, error.getMessage());
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }

    /** Kafka did not take the question. */
    static final class AgentUnavailableException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        AgentUnavailableException(Throwable cause) {
            super("the question could not be sent to the agent", cause);
        }
    }
}
