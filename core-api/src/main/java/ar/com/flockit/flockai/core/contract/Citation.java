package ar.com.flockit.flockai.core.contract;

import java.net.URI;

/**
 * A document that supports an answer.
 *
 * @param url link to the original; null for files of the persona folder
 * @param path relative path inside the persona folder (folder files only)
 */
public record Citation(String documentId, String title, URI url, String path, String section, SourceType sourceType) {}
