import { render, screen } from '@testing-library/react';
import { SafeMarkdown } from './SafeMarkdown.tsx';

const CITED = 'https://wiki.example.com/rollback';

function renderAnswer(text: string) {
  return render(<SafeMarkdown text={text} links={new Set([CITED])} />);
}

describe('SafeMarkdown', () => {
  it('renders Markdown', () => {
    renderAnswer('Pasos:\n\n1. Ejecutá **rollback-prod**\n2. Revisá `Grafana`');
    expect(screen.getByRole('list')).toBeInTheDocument();
    expect(screen.getByText('rollback-prod').tagName).toBe('STRONG');
    expect(screen.getByText('Grafana').tagName).toBe('CODE');
  });

  it('does not render HTML', () => {
    const { container } = renderAnswer(
      'Hola <script>alert(1)</script> <b onclick="x()">negrita</b>\n\n<iframe src="https://evil.example.com"></iframe>',
    );
    expect(container.querySelector('script, b, iframe')).toBeNull();
    expect(container.innerHTML).not.toContain('onclick');
  });

  it('does not load images', () => {
    const { container } = renderAnswer('Mirá ![logo](https://evil.example.com/pixel.png) esto');
    expect(container.querySelector('img')).toBeNull();
  });

  it('only links to the citations, in another tab', () => {
    renderAnswer(
      `Ver [la guía](${CITED}), [otro sitio](https://evil.example.com) y [script](javascript:alert(1)).`,
    );
    const link = screen.getByRole('link', { name: 'la guía' });
    expect(link).toHaveAttribute('href', CITED);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.getByText('otro sitio').tagName).toBe('SPAN');
    expect(screen.getByText('script').tagName).toBe('SPAN');
  });
});
