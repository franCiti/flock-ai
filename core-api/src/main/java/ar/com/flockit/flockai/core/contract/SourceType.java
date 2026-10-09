package ar.com.flockit.flockai.core.contract;

import com.fasterxml.jackson.annotation.JsonProperty;

/** Where a cited document comes from. */
public enum SourceType {
    @JsonProperty("file")
    FILE,
    @JsonProperty("email")
    EMAIL,
    @JsonProperty("email_attachment")
    EMAIL_ATTACHMENT,
    @JsonProperty("jira")
    JIRA,
    @JsonProperty("confluence")
    CONFLUENCE,
    @JsonProperty("sharepoint")
    SHAREPOINT
}
