package ar.com.flockit.flockai.core.auth;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.support.IntegrationTest;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.assertj.MvcTestResult;

/** Login, session, CSRF and public documentation (spec HU10.1, plan 6.2). */
@IntegrationTest
@AutoConfigureMockMvc
class AuthTest {

    private static final String CREDENTIALS = """
            {"username": "admin", "password": "test-admin-password"}""";

    @Autowired
    private MockMvcTester mvc;

    @Autowired
    private AppUserRepository users;

    /** A browser session: the CSRF cookie and the session, as the web app keeps them. */
    private final class Browser {
        private Cookie csrf;
        private MockHttpSession session = new MockHttpSession();

        MvcTestResult get(String path) {
            return remember(mvc.get().uri(path).session(session).exchange());
        }

        MvcTestResult post(String path, String json) {
            var request = mvc.post().uri(path).session(session).contentType(MediaType.APPLICATION_JSON);
            if (csrf != null) {
                request = request.cookie(csrf).header("X-XSRF-TOKEN", csrf.getValue());
            }
            return remember(
                    json == null ? request.exchange() : request.content(json).exchange());
        }

        private MvcTestResult remember(MvcTestResult result) {
            Cookie cookie = result.getResponse().getCookie("XSRF-TOKEN");
            if (cookie != null && !cookie.getValue().isEmpty()) {
                csrf = cookie;
            }
            HttpSession current = result.getRequest().getSession(false);
            if (current instanceof MockHttpSession mock) {
                session = mock;
            }
            return result;
        }
    }

    @Test
    void theInitialUserIsCreatedWithAHashedPassword() {
        AppUserRepository.AppUser admin = users.findByUsername("admin").orElseThrow();
        assertThat(admin.passwordHash()).startsWith("$2").doesNotContain("test-admin-password");
        assertThat(admin.enabled()).isTrue();
    }

    @Test
    void withoutASessionTheApiAnswers401AndHandsOutTheCsrfCookie() {
        MvcTestResult result = new Browser().get("/api/auth/me");
        assertThat(result).hasStatus(HttpStatus.UNAUTHORIZED);
        Cookie csrf = result.getResponse().getCookie("XSRF-TOKEN");
        assertThat(csrf).isNotNull();
        assertThat(csrf.isHttpOnly()).isFalse();
    }

    @Test
    void signInReadTheSessionAndSignOut() {
        Browser browser = new Browser();
        browser.get("/api/auth/me");

        assertThat(browser.post("/api/auth/login", CREDENTIALS)).hasStatus(HttpStatus.NO_CONTENT);
        assertThat(browser.get("/api/auth/me"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.username")
                .isEqualTo("admin");

        assertThat(browser.post("/api/auth/logout", null)).hasStatus(HttpStatus.NO_CONTENT);
        assertThat(browser.get("/api/auth/me")).hasStatus(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void aWrongPasswordIsRejectedAsProblemDetails() {
        Browser browser = new Browser();
        browser.get("/api/auth/me");
        MvcTestResult result = browser.post("/api/auth/login", "{\"username\": \"admin\", \"password\": \"wrong\"}");
        assertThat(result).hasStatus(HttpStatus.UNAUTHORIZED);
        assertThat(result).bodyJson().extractingPath("$.detail").isEqualTo("Invalid username or password");
    }

    @Test
    void anUnknownUserGetsTheSameAnswer() {
        Browser browser = new Browser();
        browser.get("/api/auth/me");
        MvcTestResult result = browser.post("/api/auth/login", "{\"username\": \"nobody\", \"password\": \"x\"}");
        assertThat(result).hasStatus(HttpStatus.UNAUTHORIZED);
        assertThat(result).bodyJson().extractingPath("$.detail").isEqualTo("Invalid username or password");
    }

    @Test
    void aPostWithoutTheCsrfTokenIsRejected() {
        assertThat(mvc.post()
                        .uri("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(CREDENTIALS))
                .hasStatus(HttpStatus.FORBIDDEN);
    }

    @Test
    void theLoginChangesTheSessionAndTheCsrfToken() {
        Browser browser = new Browser();
        browser.get("/api/auth/me");
        String tokenBefore = browser.csrf.getValue();
        String sessionBefore = browser.session.getId();

        MvcTestResult login = browser.post("/api/auth/login", CREDENTIALS);
        // The old token is cleared; the next response hands out a new one.
        assertThat(login.getResponse().getCookie("XSRF-TOKEN").getValue()).isEmpty();
        browser.get("/api/auth/me");

        assertThat(browser.csrf.getValue()).isNotEqualTo(tokenBefore);
        assertThat(browser.session.getId()).isNotEqualTo(sessionBefore);
    }

    @Test
    void theDocumentationIsPublic() {
        assertThat(mvc.get().uri("/docs/openapi")).hasStatusOk();
        assertThat(mvc.get().uri("/docs/swagger-ui/index.html")).hasStatusOk();
    }
}
