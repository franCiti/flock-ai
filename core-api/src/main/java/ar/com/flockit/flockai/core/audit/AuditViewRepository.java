package ar.com.flockit.flockai.core.audit;

import ar.com.flockit.flockai.core.contract.AuditEntry;
import java.sql.Timestamp;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.json.JsonMapper;

/** Read copy of the audit log, table {@code core.audit_entry_view} (plan 3.4, 3.5). */
@Repository
public class AuditViewRepository {

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

    /** The contract name of an enum value ({@code "partially_answered"}, {@code "RATE_LIMITED"}). */
    private String wireName(Enum<?> value) {
        return mapper.writeValueAsString(value).replace("\"", "");
    }
}
