package ar.com.flockit.flockai.core.auth;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * Creates the first user when there is none, from ADMIN_USERNAME and ADMIN_PASSWORD (plan 3.4). The
 * password is only stored as its BCrypt hash; once a user exists the variables are ignored.
 */
@Component
public class InitialUser implements ApplicationRunner {

    private static final Logger LOG = LoggerFactory.getLogger(InitialUser.class);

    private final AppUserRepository users;
    private final PasswordEncoder passwordEncoder;
    private final String username;
    private final String password;

    public InitialUser(
            AppUserRepository users,
            PasswordEncoder passwordEncoder,
            @Value("${flock.admin.username:}") String username,
            @Value("${flock.admin.password:}") String password) {
        this.users = users;
        this.passwordEncoder = passwordEncoder;
        this.username = username;
        this.password = password;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (users.count() > 0) {
            return;
        }
        if (username.isBlank() || password.isBlank()) {
            LOG.warn("No users and no initial user configured: set ADMIN_USERNAME and ADMIN_PASSWORD");
            return;
        }
        users.create(username, passwordEncoder.encode(password));
        LOG.info("Initial user created: {}", username);
    }
}
