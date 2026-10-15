import { screen, within } from '@testing-library/react';
import { FakeEventSource } from '../../test/eventSource.ts';
import { renderApp } from '../../test/renderApp.tsx';
import { accepted, error, final, token } from '../../test/replies.ts';
import { mockAuthApi, mockChatApi } from '../../test/server.ts';

async function openChat(options: Parameters<typeof mockChatApi>[0] = {}) {
  mockAuthApi({ signedIn: true });
  const api = mockChatApi(options);
  const app = renderApp('/chat');
  await screen.findByLabelText('Persona');
  return { ...app, ...api };
}

async function ask(user: Awaited<ReturnType<typeof openChat>>['user'], question: string) {
  await user.type(screen.getByLabelText('Pregunta'), question);
  await user.click(screen.getByRole('button', { name: 'Enviar' }));
}

function lastAnswer(): HTMLElement {
  const answers = screen.getAllByRole('article');
  const answer = answers.at(-1);
  if (answer === undefined) {
    throw new Error('No answer on screen');
  }
  return answer;
}

describe('chat screen', () => {
  it('sends the question and shows the answer as it streams, with its sources', async () => {
    const { user, questions } = await openChat();
    const stream = FakeEventSource.current();

    await ask(user, '¿Cómo hago un rollback?');

    expect(questions).toHaveLength(1);
    expect(questions[0]).toMatchObject({
      personaId: 'juan-plataforma',
      question: '¿Cómo hago un rollback?',
    });
    // The stream of this very conversation was open before asking.
    expect(stream.url).toBe(`/api/conversations/${questions[0]?.conversationId ?? ''}/stream`);
    expect(screen.getByText('¿Cómo hago un rollback?')).toBeInTheDocument();

    stream.emit(accepted('request-1', 120));
    expect(within(lastAnswer()).getByRole('timer')).toHaveTextContent(/^(2:00|1:59)$/);

    stream.emit(token('request-1', 1, 'Ejecutá el job '));
    stream.emit(token('request-1', 2, '`rollback-prod`'));
    // Rendered as Markdown while it streams.
    expect(lastAnswer()).toHaveTextContent('Ejecutá el job rollback-prod');

    const doc = {
      documentId: 'd1',
      title: 'Rollback',
      path: 'procedimientos/rollback.md',
      section: 'Pasos',
      sourceType: 'file',
    };
    stream.emit(
      final('request-1', 3, 'Ejecutá el job **rollback-prod** en Jenkins.', {
        citations: [
          doc,
          doc,
          { ...doc, documentId: 'd2', title: 'Guía', url: 'https://wiki.example.com/g' },
        ],
      }),
    );

    const answer = lastAnswer();
    expect(within(answer).getByText('rollback-prod').tagName).toBe('STRONG');
    expect(within(answer).queryByRole('timer')).toBeNull();
    const sources = within(answer).getAllByRole('listitem');
    expect(sources).toHaveLength(2);
    expect(sources[0]).toHaveTextContent('Rollback · Pasos · procedimientos/rollback.md');
    expect(within(answer).getByRole('link', { name: 'Guía' })).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled(); // empty question
  });

  it('shows the referral to another persona and can switch to it', async () => {
    const { user } = await openChat();
    await ask(user, '¿Cuántas ventas hubo?');

    FakeEventSource.current().emit(
      final('request-1', 1, 'No tengo información sobre eso.', {
        referral: { id: 'ana-datos', displayName: 'Ana Gómez' },
      }),
    );

    expect(lastAnswer()).toHaveTextContent('Preguntale a Ana Gómez');
    await user.click(screen.getByRole('button', { name: 'Conversar con Ana Gómez' }));
    expect(screen.getByLabelText('Persona')).toHaveValue('ana-datos');
    expect(screen.queryByRole('article')).toBeNull();
  });

  it('shows the error of the agent and retries the same question', async () => {
    const { user, questions } = await openChat();
    await ask(user, '¿Cómo hago un rollback?');

    FakeEventSource.current().emit(error('request-1', 1, true));
    const alert = within(lastAnswer()).getByRole('alert');
    expect(alert).toHaveTextContent('La respuesta tardó demasiado.');

    await user.click(within(alert).getByRole('button', { name: 'Reintentar' }));

    expect(questions.map((question) => question.question)).toEqual([
      '¿Cómo hago un rollback?',
      '¿Cómo hago un rollback?',
    ]);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getAllByRole('article')).toHaveLength(1);
  });

  it('offers no retry when it would not help', async () => {
    const { user } = await openChat();
    await ask(user, 'x');

    FakeEventSource.current().emit(error('request-1', 1, false));

    expect(within(lastAnswer()).getByRole('alert')).toHaveTextContent('demasiado larga');
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull();
  });

  it('tells when the question could not be sent', async () => {
    const { user } = await openChat({ sendStatus: 503 });
    await ask(user, '¿Hola?');

    expect(await within(lastAnswer()).findByRole('alert')).toHaveTextContent(
      'No se pudo enviar la pregunta.',
    );
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
  });

  it('counts the characters and does not send a question that is too long', async () => {
    const { user, questions } = await openChat({ maxQuestionChars: 10 });

    await user.type(screen.getByLabelText('Pregunta'), '0123456789');
    expect(screen.getByText('10 / 10')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeEnabled();

    await user.type(screen.getByLabelText('Pregunta'), 'x');
    expect(screen.getByText('11 / 10')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled();
    await user.keyboard('{Enter}');
    expect(questions).toHaveLength(0);
  });

  it('starts a new conversation with a new stream', async () => {
    const { user, questions } = await openChat();
    await ask(user, 'Primera');
    FakeEventSource.current().emit(final('request-1', 1, 'Respuesta'));
    const first = FakeEventSource.current();

    await user.click(screen.getByRole('button', { name: 'Conversación nueva' }));

    expect(first.readyState).toBe(FakeEventSource.CLOSED);
    expect(FakeEventSource.current()).not.toBe(first);
    expect(screen.queryByRole('article')).toBeNull();

    await ask(user, 'Segunda');
    expect(questions[1]?.conversationId).not.toBe(questions[0]?.conversationId);
    expect(FakeEventSource.current().url).toContain(questions[1]?.conversationId ?? '');
  });

  it('offers to reconnect when the stream gives up', async () => {
    await openChat();
    const stream = FakeEventSource.current();

    stream.fail();

    expect(await screen.findByRole('alert')).toHaveTextContent('Se perdió la conexión');
  });

  it('points to the updates screen when there are no personas yet', async () => {
    mockAuthApi({ signedIn: true });
    mockChatApi({ personas: [] });
    renderApp('/chat');

    expect(await screen.findByText(/Todavía no hay personas virtuales/)).toBeInTheDocument();
    const main = screen.getByRole('main');
    expect(within(main).getByRole('link', { name: 'Actualizaciones' })).toHaveAttribute(
      'href',
      '/sources',
    );
  });
});
