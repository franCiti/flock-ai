package ar.com.flockit.flockai.core;

import static org.assertj.core.api.Assertions.assertThat;

import ar.com.flockit.flockai.core.support.IntegrationTest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/** Flyway migrates the schema "core" as the role core_api at start-up (plan 3.4, 7.3). */
@IntegrationTest
class DatabaseMigrationTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void theMigrationsWereAppliedInTheCoreSchema() {
        List<String> applied = jdbc.queryForList(
                "SELECT version FROM core.flyway_schema_history WHERE success ORDER BY installed_rank", String.class);
        assertThat(applied).startsWith("1");
        String comment = jdbc.queryForObject("SELECT obj_description('core'::regnamespace)", String.class);
        assertThat(comment).startsWith("Core API");
    }

    @Test
    void theApplicationConnectsAsCoreApiWithTheCoreSchemaFirst() {
        assertThat(jdbc.queryForObject("SELECT current_user", String.class)).isEqualTo("core_api");
        assertThat(jdbc.queryForObject("SELECT current_schema()", String.class)).isEqualTo("core");
    }

    @Test
    void coreApiCannotReadTheSchemasOfPython() {
        // Java only gets the agent data through Kafka (plan 3.1, 3.5).
        Boolean knowledge = jdbc.queryForObject("SELECT has_schema_privilege('knowledge', 'USAGE')", Boolean.class);
        Boolean agent = jdbc.queryForObject("SELECT has_schema_privilege('agent', 'USAGE')", Boolean.class);
        assertThat(knowledge).isFalse();
        assertThat(agent).isFalse();
    }
}
