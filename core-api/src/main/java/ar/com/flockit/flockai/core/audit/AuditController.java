package ar.com.flockit.flockai.core.audit;

import ar.com.flockit.flockai.core.contract.AuditEntry;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.time.Instant;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.web.ErrorResponseException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

/** The audit log for the operator (spec HU8, plan 6.3). */
@RestController
@RequestMapping(value = "/api/audit", produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "audit", description = "Record of the processed questions")
public class AuditController {

    private final AuditViewRepository audit;
    private final JsonMapper mapper;

    public AuditController(AuditViewRepository audit, JsonMapper mapper) {
        this.audit = audit;
        this.mapper = mapper;
    }

    @GetMapping
    @Operation(summary = "Entries of the audit log, newest first; the filters apply together")
    public AuditViewRepository.AuditPage find(
            @Parameter(description = "Page number, from 0") @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @RequestParam(required = false) String personaId,
            @Parameter(description = "First moment included (ISO 8601)")
                    @RequestParam(required = false)
                    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                    Instant from,
            @Parameter(description = "First moment excluded (ISO 8601)")
                    @RequestParam(required = false)
                    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                    Instant to,
            @Parameter(
                            description = "Entries with any of these outcomes",
                            array = @ArraySchema(schema = @Schema(implementation = AuditEntry.AuditOutcome.class)))
                    @RequestParam(required = false)
                    List<String> outcome,
            @Parameter(
                            description = "Entries with any of these flags",
                            array = @ArraySchema(schema = @Schema(implementation = AuditEntry.Flag.class)))
                    @RequestParam(required = false)
                    List<String> flag,
            @Parameter(description = "Whether the answer suggested another persona") @RequestParam(required = false)
                    Boolean referred) {
        AuditViewRepository.AuditFilter filter = new AuditViewRepository.AuditFilter(
                personaId,
                from,
                to,
                parse(outcome, AuditEntry.AuditOutcome.class, "outcome"),
                parse(flag, AuditEntry.Flag.class, "flag"),
                referred);
        return audit.find(filter, page, size);
    }

    /** Reads the contract names of an enum ({@code partially_answered}); an unknown one is a 400. */
    private <E extends Enum<E>> List<E> parse(List<String> values, Class<E> type, String parameter) {
        if (values == null) {
            return List.of();
        }
        return values.stream()
                .map(value -> {
                    try {
                        return mapper.convertValue(value, type);
                    } catch (JacksonException error) {
                        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                                HttpStatus.BAD_REQUEST, "unknown " + parameter + ": " + value);
                        throw new ErrorResponseException(HttpStatus.BAD_REQUEST, problem, error);
                    }
                })
                .toList();
    }
}
