package ar.com.flockit.flockai.core.persona;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.support.IntegrationTest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpStatus;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.assertj.MvcTestResult;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** The personas and the settings the web app reads (spec HU10.2, HU15.5, plan 6.3). */
@IntegrationTest
@AutoConfigureMockMvc
class PersonasAndConfigTest {

    @Autowired
    private MockMvcTester mvc;

    @Autowired
    private PersonaViewRepository personas;

    @Autowired
    private JsonMapper mapper;

    @Test
    @WithMockUser
    void thePersonasComeByDisplayName() {
        String suffix = UUID.randomUUID().toString();
        personas.upsert("zz-" + suffix, "Zulema " + suffix, Instant.now());
        personas.upsert("aa-" + suffix, "Zoe " + suffix, Instant.now());

        JsonNode list = get("/api/personas");
        List<String> ids = new ArrayList<>();
        list.forEach(persona -> ids.add(persona.get("id").asString()));
        assertThat(ids).containsSubsequence("aa-" + suffix, "zz-" + suffix);
        JsonNode zoe = list.get(ids.indexOf("aa-" + suffix));
        assertThat(zoe.get("displayName").asString()).isEqualTo("Zoe " + suffix);
    }

    @Test
    @WithMockUser
    void theConfigHasTheQuestionLimit() {
        assertThat(get("/api/config").get("maxQuestionChars").asInt()).isEqualTo(2000);
    }

    @Test
    void bothNeedASession() {
        assertThat(mvc.get().uri("/api/personas").exchange()).hasStatus(HttpStatus.UNAUTHORIZED);
        assertThat(mvc.get().uri("/api/config").exchange()).hasStatus(HttpStatus.UNAUTHORIZED);
    }

    private JsonNode get(String path) {
        MvcTestResult result = mvc.get().uri(path).exchange();
        assertThat(result).hasStatus(HttpStatus.OK);
        return mapper.readTree(result.getResponse().getContentAsByteArray());
    }
}
