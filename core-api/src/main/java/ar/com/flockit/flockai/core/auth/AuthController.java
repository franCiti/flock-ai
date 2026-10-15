package ar.com.flockit.flockai.core.auth;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Session of the web app: login, current user (plan 6.2, 6.3). Logout is Spring Security's. */
@RestController
@RequestMapping("/api/auth")
@Tag(name = "auth", description = "Session of the web app (cookie)")
public class AuthController {

    /** Username and password of a login. */
    public record LoginRequest(
            @NotBlank String username, @NotBlank String password) {}

    /** The signed-in user. */
    public record CurrentUser(String username) {}

    private final AuthenticationManager authentication;
    private final SessionAuthenticationStrategy sessionStrategy;
    private final SecurityContextRepository contexts;

    public AuthController(
            AuthenticationManager authentication,
            SessionAuthenticationStrategy sessionStrategy,
            SecurityContextRepository contexts) {
        this.authentication = authentication;
        this.sessionStrategy = sessionStrategy;
        this.contexts = contexts;
    }

    @PostMapping("/login")
    @Operation(summary = "Sign in: opens a session (cookie)")
    @ApiResponse(responseCode = "204", description = "Signed in")
    @ApiResponse(responseCode = "401", description = "Wrong username or password")
    public ResponseEntity<Void> login(
            @Valid @RequestBody LoginRequest login, HttpServletRequest request, HttpServletResponse response) {
        Authentication user = authentication.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(login.username(), login.password()));
        sessionStrategy.onAuthentication(user, request, response);
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(user);
        SecurityContextHolder.setContext(context);
        contexts.saveContext(context, request, response);
        return ResponseEntity.noContent().build();
    }

    @GetMapping(value = "/me", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "The signed-in user")
    @ApiResponse(responseCode = "200", description = "There is a session")
    @ApiResponse(responseCode = "401", description = "No session")
    public CurrentUser me(Authentication user) {
        return new CurrentUser(user.getName());
    }

    /** Wrong credentials, unknown or disabled user: the same answer, so it reveals nothing. */
    @ExceptionHandler(AuthenticationException.class)
    ResponseEntity<ProblemDetail> loginFailed() {
        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(HttpStatus.UNAUTHORIZED, "Invalid username or password");
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(problem);
    }
}
