package ar.com.flockit.flockai.core.ingestion;

import ar.com.flockit.flockai.core.contract.IngestionJob;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Knowledge updates: manual trigger and history (spec HU4.5, HU4.8, plan 6.3). */
@RestController
@RequestMapping(value = "/api/ingestion/runs", produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "ingestion", description = "Knowledge updates")
public class IngestionRunsController {

    /** The job of a requested update. */
    public record RequestedRun(UUID jobId) {}

    private final IngestionService ingestion;
    private final IngestionRunRepository runs;

    public IngestionRunsController(IngestionService ingestion, IngestionRunRepository runs) {
        this.ingestion = ingestion;
        this.runs = runs;
    }

    @PostMapping
    @Operation(summary = "Update the knowledge base now")
    @ApiResponse(responseCode = "202", description = "Requested; its progress shows in the history")
    @ApiResponse(
            responseCode = "503",
            description = "Kafka is not available",
            content =
                    @Content(
                            mediaType = "application/problem+json",
                            schema = @Schema(implementation = ProblemDetail.class)))
    public ResponseEntity<RequestedRun> request() {
        UUID jobId = ingestion.request(IngestionJob.Trigger.MANUAL);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(new RequestedRun(jobId));
    }

    @GetMapping
    @Operation(summary = "History of the knowledge updates, newest first")
    public List<IngestionRunRepository.IngestionRun> history(
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit) {
        return runs.findRecent(limit);
    }

    @ExceptionHandler(IngestionService.IngestionUnavailableException.class)
    ResponseEntity<ProblemDetail> unavailable(IngestionService.IngestionUnavailableException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.SERVICE_UNAVAILABLE, error.getMessage());
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}
