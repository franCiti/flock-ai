package ar.com.flockit.flockai.core.contract;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Request to update the knowledge base (internal). Published to {@code ingestion.jobs}. Persona
 * folders are always scanned.
 *
 * @param sources every external source of every persona; documents of sources not listed are removed
 */
public record IngestionJob(int version, UUID jobId, Trigger trigger, Instant requestedAt, List<Source> sources) {

    /** What started the update. */
    public enum Trigger {
        @JsonProperty("scheduled")
        SCHEDULED,
        @JsonProperty("manual")
        MANUAL
    }

    /** An external source of a persona, resolved by its {@code type}. */
    @JsonTypeInfo(use = JsonTypeInfo.Id.NAME, property = "type")
    @JsonSubTypes({
        @JsonSubTypes.Type(value = JiraSource.class, name = "jira"),
        @JsonSubTypes.Type(value = ConfluenceSource.class, name = "confluence"),
        @JsonSubTypes.Type(value = SharePointSource.class, name = "sharepoint")
    })
    public sealed interface Source permits JiraSource, ConfluenceSource, SharePointSource {

        String sourceId();

        String personaId();
    }

    /** Issues of a Jira project. */
    public record JiraSource(String sourceId, String personaId, JiraScope scope) implements Source {}

    /** Selects the Jira project. */
    public record JiraScope(String projectKey) {}

    /** Pages of a Confluence space. */
    public record ConfluenceSource(String sourceId, String personaId, ConfluenceScope scope) implements Source {}

    /** Selects the Confluence space. */
    public record ConfluenceScope(String spaceKey) {}

    /** Files of a SharePoint folder. */
    public record SharePointSource(String sourceId, String personaId, SharePointScope scope) implements Source {}

    /** Selects the SharePoint site and folder. */
    public record SharePointScope(URI siteUrl, String folderPath) {}
}
