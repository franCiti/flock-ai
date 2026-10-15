package ar.com.flockit.flockai.core.persona;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** Read copy of the personas, table {@code core.persona_view} (plan 3.4, 3.5). */
@Repository
public class PersonaViewRepository {

    /** A persona available to the web app. */
    public record PersonaView(String id, String displayName) {}

    private final JdbcClient jdbc;

    public PersonaViewRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    /** Adds or updates a persona, unless the copy already has newer data. */
    public void upsert(String id, String displayName, Instant at) {
        jdbc.sql("""
                        INSERT INTO persona_view (id, display_name, updated_at) VALUES (?, ?, ?)
                        ON CONFLICT (id) DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            updated_at = EXCLUDED.updated_at
                        WHERE persona_view.updated_at <= EXCLUDED.updated_at
                        """).params(id, displayName, Timestamp.from(at)).update();
    }

    public void delete(String id) {
        jdbc.sql("DELETE FROM persona_view WHERE id = ?").param(id).update();
    }

    public List<PersonaView> findAll() {
        return jdbc.sql("SELECT id, display_name FROM persona_view ORDER BY display_name, id")
                .query(PersonaView.class)
                .list();
    }
}
