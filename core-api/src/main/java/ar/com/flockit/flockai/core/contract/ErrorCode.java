package ar.com.flockit.flockai.core.contract;

/** Why a request ended without an answer. */
public enum ErrorCode {
    INVALID_REQUEST,
    UNSUPPORTED_VERSION,
    PERSONA_NOT_FOUND,
    QUESTION_TOO_LONG,
    RATE_LIMITED,
    TIMEOUT,
    LLM_UNAVAILABLE,
    INTERNAL_ERROR
}
