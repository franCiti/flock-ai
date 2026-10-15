package ar.com.flockit.flockai.core.ingestion;

import ar.com.flockit.flockai.core.contract.IngestionEvent;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/**
 * Read copy of the knowledge updates, table {@code core.ingestion_run_view} (plan 3.4, 3.5).
 *
 * <p>Every change is an upsert by job id that gives the same result when applied twice. A finished
 * run (completed, failed or rejected) is never reopened by a repeated "started".
 */
@Repository
public class IngestionRunRepository {

    /**
     * A knowledge update as the web app shows it (spec HU4.5).
     *
     * @param trigger {@code scheduled} or {@code manual}; null if the Core API did not request it
     * @param status {@code requested}, {@code running}, {@code completed}, {@code failed} or {@code rejected}
     * @param personas summary of each updated persona, by persona id
     * @param reason why it failed or was rejected
     */
    public record IngestionRun(
            UUID jobId,
            String trigger,
            String status,
            Instant requestedAt,
            Instant startedAt,
            Instant finishedAt,
            IngestionEvent.Totals totals,
            List<IngestionEvent.PersonaSummary> personas,
            List<String> removedPersonas,
            String reason) {}

    private static final TypeReference<Map<String, IngestionEvent.PersonaSummary>> PERSONAS = new TypeReference<>() {};
    private static final TypeReference<List<String>> STRINGS = new TypeReference<>() {};

    private final JdbcClient jdbc;
    private final JsonMapper mapper;

    public IngestionRunRepository(JdbcClient jdbc, JsonMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    /** The latest updates, newest first (by when they were requested or started). */
    public List<IngestionRun> findRecent(int limit) {
        return jdbc.sql("""
                        SELECT job_id, trigger, status, requested_at, started_at, finished_at,
                               totals::text AS totals, personas::text AS personas,
                               removed_personas::text AS removed_personas, reason
                        FROM ingestion_run_view
                        ORDER BY coalesce(requested_at, started_at) DESC NULLS LAST, job_id
                        LIMIT ?
                        """).param(limit).query(this::toRun).list();
    }

    private IngestionRun toRun(ResultSet row, int rowNumber) throws SQLException {
        String totals = row.getString("totals");
        List<IngestionEvent.PersonaSummary> personas =
                mapper.readValue(row.getString("personas"), PERSONAS).values().stream()
                        .sorted(Comparator.comparing(IngestionEvent.PersonaSummary::personaId))
                        .toList();
        return new IngestionRun(
                row.getObject("job_id", UUID.class),
                row.getString("trigger"),
                row.getString("status"),
                instant(row.getTimestamp("requested_at")),
                instant(row.getTimestamp("started_at")),
                instant(row.getTimestamp("finished_at")),
                totals == null ? null : mapper.readValue(totals, IngestionEvent.Totals.class),
                personas,
                mapper.readValue(row.getString("removed_personas"), STRINGS),
                row.getString("reason"));
    }

    private static Instant instant(Timestamp timestamp) {
        return timestamp == null ? null : timestamp.toInstant();
    }

    /** The Core API published the job (T35): the run exists before the ingestion answers. */
    public void requested(UUID jobId, String trigger, Instant at) {
        jdbc.sql("""
                        INSERT INTO ingestion_run_view (job_id, trigger, status, requested_at, updated_at)
                        VALUES (?, ?, 'requested', ?, ?)
                        ON CONFLICT (job_id) DO UPDATE SET
                            trigger = EXCLUDED.trigger, requested_at = EXCLUDED.requested_at
                        """).params(jobId, trigger, ts(at), ts(at)).update();
    }

    public void started(UUID jobId, Instant at) {
        jdbc.sql("""
                        INSERT INTO ingestion_run_view (job_id, status, started_at, updated_at)
                        VALUES (?, 'running', ?, ?)
                        ON CONFLICT (job_id) DO UPDATE SET
                            status = CASE WHEN ingestion_run_view.finished_at IS NULL
                                          THEN 'running' ELSE ingestion_run_view.status END,
                            started_at = EXCLUDED.started_at,
                            updated_at = greatest(ingestion_run_view.updated_at, EXCLUDED.updated_at)
                        """).params(jobId, ts(at), ts(at)).update();
    }

    /** Adds (or replaces) the summary of one persona; the run is created if it was not known. */
    public void personaCompleted(UUID jobId, String personaId, String summaryJson, Instant at) {
        jdbc.sql("""
                        INSERT INTO ingestion_run_view (job_id, status, personas, updated_at)
                        VALUES (:job, 'running', jsonb_build_object(:persona, CAST(:summary AS jsonb)), :at)
                        ON CONFLICT (job_id) DO UPDATE SET
                            personas = ingestion_run_view.personas
                                       || jsonb_build_object(:persona, CAST(:summary AS jsonb)),
                            updated_at = greatest(ingestion_run_view.updated_at, EXCLUDED.updated_at)
                        """)
                .param("job", jobId)
                .param("persona", personaId)
                .param("summary", summaryJson)
                .param("at", ts(at))
                .update();
    }

    public void personaRemoved(UUID jobId, String personaId, Instant at) {
        jdbc.sql("""
                        INSERT INTO ingestion_run_view (job_id, status, removed_personas, updated_at)
                        VALUES (:job, 'running', jsonb_build_array(:persona), :at)
                        ON CONFLICT (job_id) DO UPDATE SET
                            removed_personas = CASE
                                WHEN ingestion_run_view.removed_personas @> jsonb_build_array(:persona)
                                THEN ingestion_run_view.removed_personas
                                ELSE ingestion_run_view.removed_personas || jsonb_build_array(:persona) END,
                            updated_at = greatest(ingestion_run_view.updated_at, EXCLUDED.updated_at)
                        """)
                .param("job", jobId)
                .param("persona", personaId)
                .param("at", ts(at))
                .update();
    }

    /** The run ended: completed (with its totals), failed or rejected (with the reason). */
    public void finished(UUID jobId, String status, String totalsJson, String reason, Instant at) {
        jdbc.sql("""
                        INSERT INTO ingestion_run_view (job_id, status, finished_at, totals, reason, updated_at)
                        VALUES (:job, :status, :at, CAST(:totals AS jsonb), :reason, :at)
                        ON CONFLICT (job_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            finished_at = EXCLUDED.finished_at,
                            totals = coalesce(EXCLUDED.totals, ingestion_run_view.totals),
                            reason = coalesce(EXCLUDED.reason, ingestion_run_view.reason),
                            updated_at = greatest(ingestion_run_view.updated_at, EXCLUDED.updated_at)
                        """)
                .param("job", jobId)
                .param("status", status)
                .param("at", ts(at))
                .param("totals", totalsJson)
                .param("reason", reason)
                .update();
    }

    private static Timestamp ts(Instant at) {
        return Timestamp.from(at);
    }
}
