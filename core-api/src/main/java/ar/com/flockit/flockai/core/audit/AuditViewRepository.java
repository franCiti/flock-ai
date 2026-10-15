package ar.com.flockit.flockai.core.audit;

import ar.com.flockit.flockai.core.contract.AuditEntry;
import ar.com.flockit.flockai.core.contract.Citation;
import ar.com.flockit.flockai.core.contract.ErrorCode;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/** Read copy of the audit log, table {@code core.audit_entry_view} (plan 3.4, 3.5). */
@Repository
public class AuditViewRepository {

    /** An entry of the audit log as the web app shows it. */
    public record AuditRecord(
            UUID id,
            UUID requestId,
            String clientId,
            String conversationId,
            String personaId,
            String question,
            String answer,
            AuditEntry.AuditOutcome outcome,
            ErrorCode errorCode,
            List<Citation> citations,
            String referralPersonaId,
            List<AuditEntry.Flag> flags,
            String llmModel,
            String promptVersion,
            Integer firstTokenMs,
            Integer totalMs,
            Instant createdAt) {}

    /**
     * Which entries to list; every criterion is optional and they all apply together.
     *
     * @param from first moment included
     * @param to first moment excluded
     * @param outcomes entries with any of these outcomes
     * @param flags entries with any of these flags
     * @param referred whether the answer suggested another persona
     */
    public record AuditFilter(
            String personaId,
            Instant from,
            Instant to,
            List<AuditEntry.AuditOutcome> outcomes,
            List<AuditEntry.Flag> flags,
            Boolean referred) {}

    /** A page of entries, newest first. */
    public record AuditPage(List<AuditRecord> items, int page, int size, long totalItems) {}

    private static final TypeReference<List<Citation>> CITATIONS = new TypeReference<>() {};

    private static final String COLUMNS = "id, request_id, client_id, conversation_id, persona_id, question, "
            + "answer, outcome, error_code, citations::text AS citations, referral_persona_id, flags, llm_model, "
            + "prompt_version, first_token_ms, total_ms, created_at";

    private final JdbcClient jdbc;
    private final JsonMapper mapper;

    public AuditViewRepository(JdbcClient jdbc, JsonMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    /** Stores an entry; an entry is never modified, so a repeated one changes nothing. */
    public void save(AuditEntry entry) {
        String[] flags = entry.flags() == null
                ? new String[0]
                : entry.flags().stream().map(this::wireName).toArray(String[]::new);
        jdbc.sql("""
                        INSERT INTO audit_entry_view (id, request_id, client_id, conversation_id, persona_id,
                            question, answer, outcome, error_code, citations, referral_persona_id, flags,
                            llm_model, prompt_version, first_token_ms, total_ms, created_at)
                        VALUES (:id, :requestId, :clientId, :conversationId, :personaId, :question, :answer,
                            :outcome, :errorCode, CAST(:citations AS jsonb), :referral, :flags, :llmModel,
                            :promptVersion, :firstTokenMs, :totalMs, :createdAt)
                        ON CONFLICT (id) DO NOTHING
                        """)
                .param("id", entry.auditId())
                .param("requestId", entry.requestId())
                .param("clientId", entry.clientId())
                .param("conversationId", entry.conversationId())
                .param("personaId", entry.personaId())
                .param("question", entry.question())
                .param("answer", entry.answer())
                .param("outcome", wireName(entry.outcome()))
                .param("errorCode", entry.errorCode() == null ? null : wireName(entry.errorCode()))
                .param(
                        "citations",
                        mapper.writeValueAsString(entry.citations() == null ? List.of() : entry.citations()))
                .param("referral", entry.referralPersonaId())
                .param("flags", flags)
                .param("llmModel", entry.llmModel())
                .param("promptVersion", entry.promptVersion())
                .param("firstTokenMs", entry.firstTokenMs())
                .param("totalMs", entry.totalMs())
                .param("createdAt", Timestamp.from(entry.createdAt()))
                .update();
    }

    /** The entries that match the filter, newest first. */
    public AuditPage find(AuditFilter filter, int page, int size) {
        List<String> conditions = new ArrayList<>();
        Map<String, Object> params = new HashMap<>();
        if (filter.personaId() != null) {
            conditions.add("persona_id = :personaId");
            params.put("personaId", filter.personaId());
        }
        if (filter.from() != null) {
            conditions.add("created_at >= :from");
            params.put("from", Timestamp.from(filter.from()));
        }
        if (filter.to() != null) {
            conditions.add("created_at < :to");
            params.put("to", Timestamp.from(filter.to()));
        }
        if (filter.outcomes() != null && !filter.outcomes().isEmpty()) {
            conditions.add("outcome IN (:outcomes)");
            params.put(
                    "outcomes", filter.outcomes().stream().map(this::wireName).toList());
        }
        if (filter.flags() != null && !filter.flags().isEmpty()) {
            conditions.add("flags && CAST(:flags AS text[])");
            params.put("flags", filter.flags().stream().map(this::wireName).toArray(String[]::new));
        }
        if (filter.referred() != null) {
            conditions.add(filter.referred() ? "referral_persona_id IS NOT NULL" : "referral_persona_id IS NULL");
        }
        // Only fixed fragments go into the SQL; the values are parameters.
        String where = conditions.isEmpty() ? "" : " WHERE " + String.join(" AND ", conditions);

        long total = jdbc.sql("SELECT count(*) FROM audit_entry_view" + where)
                .params(params)
                .query(Long.class)
                .single();
        List<AuditRecord> items = jdbc.sql("SELECT " + COLUMNS + " FROM audit_entry_view" + where
                        + " ORDER BY created_at DESC, id LIMIT :limit OFFSET :offset")
                .params(params)
                .param("limit", size)
                .param("offset", (long) page * size)
                .query(this::toRecord)
                .list();
        return new AuditPage(items, page, size, total);
    }

    private AuditRecord toRecord(ResultSet row, int rowNumber) throws SQLException {
        String errorCode = row.getString("error_code");
        String[] flags = (String[]) row.getArray("flags").getArray();
        return new AuditRecord(
                row.getObject("id", UUID.class),
                row.getObject("request_id", UUID.class),
                row.getString("client_id"),
                row.getString("conversation_id"),
                row.getString("persona_id"),
                row.getString("question"),
                row.getString("answer"),
                mapper.convertValue(row.getString("outcome"), AuditEntry.AuditOutcome.class),
                errorCode == null ? null : mapper.convertValue(errorCode, ErrorCode.class),
                mapper.readValue(row.getString("citations"), CITATIONS),
                row.getString("referral_persona_id"),
                Arrays.stream(flags)
                        .map(flag -> mapper.convertValue(flag, AuditEntry.Flag.class))
                        .toList(),
                row.getString("llm_model"),
                row.getString("prompt_version"),
                row.getObject("first_token_ms", Integer.class),
                row.getObject("total_ms", Integer.class),
                row.getTimestamp("created_at").toInstant());
    }

    /** The contract name of an enum value ({@code "partially_answered"}, {@code "RATE_LIMITED"}). */
    private String wireName(Enum<?> value) {
        return mapper.writeValueAsString(value).replace("\"", "");
    }
}
