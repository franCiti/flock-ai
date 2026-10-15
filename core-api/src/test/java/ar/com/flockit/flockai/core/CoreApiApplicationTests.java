package ar.com.flockit.flockai.core;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.support.IntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

@IntegrationTest
@AutoConfigureMockMvc
class CoreApiApplicationTests {

    @Autowired
    private MockMvcTester mvc;

    @Test
    void healthIsUp() {
        assertThat(mvc.get().uri("/actuator/health"))
                .hasStatus(HttpStatus.OK)
                .bodyJson()
                .extractingPath("$.status")
                .isEqualTo("UP");
    }

    @Test
    void openApiDocumentIsGeneratedFromTheCode() {
        assertThat(mvc.get().uri("/docs/openapi"))
                .hasStatus(HttpStatus.OK)
                .bodyJson()
                .extractingPath("$.openapi")
                .asString()
                .startsWith("3.");
    }

    @Test
    void swaggerUiIsServed() {
        assertThat(mvc.get().uri("/docs/swagger-ui/index.html")).hasStatus(HttpStatus.OK);
    }
}
