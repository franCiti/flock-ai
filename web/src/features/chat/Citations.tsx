import type { Citation } from '../../api/chat.ts';
import { citationKey, isWebUrl, uniqueCitations } from './citationLinks.ts';
import styles from './ChatPage.module.css';

/** The sources of an answer: title, section and link, or the path of a folder file (plan 6.6). */
export function Citations({ citations }: { citations: Citation[] }) {
  const unique = uniqueCitations(citations);
  if (unique.length === 0) {
    return null;
  }
  return (
    <div className={styles.citations}>
      <h3 className={styles.citationsTitle}>Fuentes</h3>
      <ul>
        {unique.map((citation) => (
          <li key={citationKey(citation)}>
            {isWebUrl(citation.url) ? (
              <a href={citation.url} target="_blank" rel="noopener noreferrer">
                {citation.title}
              </a>
            ) : (
              <span className={styles.citationTitle}>{citation.title}</span>
            )}
            {citation.section ? <span> · {citation.section}</span> : null}
            {!isWebUrl(citation.url) && citation.path ? (
              <span className={styles.citationPath}> · {citation.path}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
