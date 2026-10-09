package ar.com.flockit.flockai.core.contract;

import com.fasterxml.jackson.annotation.JsonProperty;

/** How the agent handled a question that got a final reply. */
public enum Outcome {
    @JsonProperty("answered")
    ANSWERED,
    @JsonProperty("partially_answered")
    PARTIALLY_ANSWERED,
    @JsonProperty("no_information")
    NO_INFORMATION,
    @JsonProperty("out_of_scope")
    OUT_OF_SCOPE,
    @JsonProperty("small_talk")
    SMALL_TALK,
    @JsonProperty("about_assistant")
    ABOUT_ASSISTANT
}
