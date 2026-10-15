package ar.com.flockit.flockai.core.auth;

import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** Users of the web app, table {@code core.app_user} (plan 3.4). */
@Repository
public class AppUserRepository {

    /** A stored user; the password only as its BCrypt hash. */
    public record AppUser(String username, String passwordHash, boolean enabled) {}

    private final JdbcClient jdbc;

    public AppUserRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<AppUser> findByUsername(String username) {
        return jdbc.sql("SELECT username, password_hash, enabled FROM app_user WHERE username = ?")
                .param(username)
                .query(AppUser.class)
                .optional();
    }

    public long count() {
        return jdbc.sql("SELECT count(*) FROM app_user").query(Long.class).single();
    }

    public void create(String username, String passwordHash) {
        jdbc.sql("INSERT INTO app_user (username, password_hash) VALUES (?, ?)")
                .params(username, passwordHash)
                .update();
    }
}
