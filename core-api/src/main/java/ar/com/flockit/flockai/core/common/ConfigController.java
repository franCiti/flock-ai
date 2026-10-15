package ar.com.flockit.flockai.core.common;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Settings the web app needs (spec HU15.5, plan 6.3). */
@RestController
@Tag(name = "config", description = "Settings for the web app")
public class ConfigController {

    /**
     * Settings for the web app.
     *
     * @param maxQuestionChars longest question the agent takes (MAX_QUESTION_CHARS)
     */
    public record ClientConfig(int maxQuestionChars) {}

    private final ClientConfig config;

    public ConfigController(@Value("${flock.chat.max-question-chars}") int maxQuestionChars) {
        this.config = new ClientConfig(maxQuestionChars);
    }

    @GetMapping(value = "/api/config", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Settings for the web app")
    public ClientConfig config() {
        return config;
    }
}
