package ar.com.flockit.flockai.core;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * Keeps the copy of the OpenAPI spec that the web app generates its types from (plan 6.7) equal to
 * the one the API publishes. Run with {@code -Dopenapi.update=true} to rewrite the copy.
 */
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiSnapshotTest {

    private static final Path SNAPSHOT = Path.of(System.getProperty("openapi.snapshot", "../web/src/api/openapi.json"));

    private static final JsonMapper MAPPER =
            JsonMapper.builder().enable(SerializationFeature.INDENT_OUTPUT).build();

    @Autowired
    private MockMvcTester mvc;

    @Test
    void webCopyOfOpenApiSpecIsUpToDate() throws IOException {
        String published =
                mvc.get().uri("/docs/openapi").exchange().getResponse().getContentAsString();
        ObjectNode spec = (ObjectNode) MAPPER.readTree(published);
        // The server URL depends on how the API is reached; the web app always uses relative paths.
        spec.remove("servers");
        // Always LF, whatever the platform line separator Jackson uses.
        String expected = MAPPER.writeValueAsString(spec).replace("\r\n", "\n") + "\n";

        if (Boolean.getBoolean("openapi.update")) {
            Files.writeString(SNAPSHOT, expected, StandardCharsets.UTF_8);
        }

        assertThat(SNAPSHOT)
                .as("outdated copy; run ./mvnw test -Dtest=OpenApiSnapshotTest -Dopenapi.update=true")
                .exists();
        String copy = Files.readString(SNAPSHOT, StandardCharsets.UTF_8).replace("\r\n", "\n");
        assertThat(copy)
                .as("outdated copy; run ./mvnw test -Dtest=OpenApiSnapshotTest -Dopenapi.update=true")
                .isEqualTo(expected);
    }
}
