import type { Citation } from '../../api/chat.ts';

/** Only web links open: anything else (javascript:, data:, file:) is shown as text. */
export function isWebUrl(url: string | null | undefined): url is string {
  return url != null && /^https?:\/\//i.test(url);
}

/** The links an answer may contain: those of its citations (spec HU15.6). */
export function citationLinks(citations: Citation[]): Set<string> {
  return new Set(citations.flatMap((citation) => (isWebUrl(citation.url) ? [citation.url] : [])));
}

/** Several fragments of the same section count as one source. */
export function uniqueCitations(citations: Citation[]): Citation[] {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const key = citationKey(citation);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function citationKey(citation: Citation): string {
  return [
    citation.documentId,
    citation.section ?? '',
    citation.url ?? '',
    citation.path ?? '',
  ].join('|');
}
