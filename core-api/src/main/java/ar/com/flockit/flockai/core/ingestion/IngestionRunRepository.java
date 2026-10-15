package ar.com.flockit.flockai.core.ingestion;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * Read copy of the knowledge updates, table {@code core.ingestion_run_view} (plan 3.4, 3.5).
 *
 * <p>Every change is an upsert by job id that gives the same result when applied twice. A finished
 * run (completed, failed or rejected) is never reopened by a repeated "started".
 */
@Repository
public class IngestionRunRepository {

    private final JdbcClient jdbc;

    public IngestionRunRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
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
