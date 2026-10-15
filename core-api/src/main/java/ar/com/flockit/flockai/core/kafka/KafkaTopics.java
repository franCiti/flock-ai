package ar.com.flockit.flockai.core.kafka;

/** Kafka topics the Core API uses (plan 2.2 and 6.5). The ACLs only allow these. */
public final class KafkaTopics {

    /** Questions of the chat, to the agent (produce). */
    public static final String AGENT_REQUESTS = "agent.requests";

    /** Replies of the agent to this client app, {@code agent.replies.<clientId>} (consume). */
    public static final String AGENT_REPLIES = "agent.replies.core-api";

    /** Audit log of the agent, for its read copy (consume). */
    public static final String AGENT_AUDIT = "agent.audit";

    /** Knowledge updates, scheduled or manual (produce). */
    public static final String INGESTION_JOBS = "ingestion.jobs";

    /** Progress and result of the knowledge updates (consume). */
    public static final String INGESTION_EVENTS = "ingestion.events";

    private KafkaTopics() {}
}
