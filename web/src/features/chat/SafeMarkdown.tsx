import Markdown, { type Components } from 'react-markdown';

/**
 * Renders an answer of the agent (plan 6.6, spec HU15.6): no HTML, no images, and links only when
 * they point to one of the citations, opened in another tab. The agent already sanitizes its
 * answers (plan 4.3); this is the second barrier.
 */
export function SafeMarkdown({ text, links }: { text: string; links: ReadonlySet<string> }) {
  const components: Components = {
    a: ({ href, children }) =>
      href !== undefined && links.has(href) ? (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      ) : (
        <span>{children}</span>
      ),
  };
  return (
    <Markdown skipHtml disallowedElements={['img']} components={components}>
      {text}
    </Markdown>
  );
}
