import { accepted, error, final, token } from '../../test/replies.ts';
import {
  answerDuration,
  conversationReducer,
  formatSeconds,
  newConversation,
  pendingTurn,
  secondsLeft,
  type Conversation,
  type ConversationAction,
} from './conversation.ts';

function run(...actions: ConversationAction[]): Conversation {
  return actions.reduce(conversationReducer, newConversation('conversation'));
}

const asked: ConversationAction = { type: 'asked', turnId: 't1', question: '¿Cómo?', at: 0 };

describe('assembling the streamed answer', () => {
  it('appends the tokens and replaces them with the final answer', () => {
    const streaming = run(
      asked,
      { type: 'sent', turnId: 't1', requestId: 'r1' },
      { type: 'reply', reply: accepted('r1'), receivedAt: 0 },
      { type: 'reply', reply: token('r1', 1, 'Para hacer '), receivedAt: 0 },
      { type: 'reply', reply: token('r1', 2, 'un rollback'), receivedAt: 0 },
    );
    expect(streaming.turns[0]).toMatchObject({
      status: 'streaming',
      text: 'Para hacer un rollback',
    });

    const done = conversationReducer(streaming, {
      type: 'reply',
      reply: final('r1', 3, 'Para hacer un **rollback**, ejecutá el job.'),
      receivedAt: 0,
    });
    expect(done.turns[0]).toMatchObject({
      status: 'done',
      text: 'Para hacer un **rollback**, ejecutá el job.',
    });
    expect(pendingTurn(done)).toBeUndefined();
  });

  it('takes replies that arrive before the answer to the POST', () => {
    const conversation = run(
      asked,
      { type: 'reply', reply: accepted('r1'), receivedAt: 0 },
      { type: 'reply', reply: token('r1', 1, 'Hola'), receivedAt: 0 },
      { type: 'sent', turnId: 't1', requestId: 'r1' },
    );
    expect(conversation.turns[0]).toMatchObject({ requestId: 'r1', text: 'Hola' });
  });

  it('ignores replies of other requests and repeated ones', () => {
    const conversation = run(
      asked,
      { type: 'sent', turnId: 't1', requestId: 'r1' },
      { type: 'reply', reply: token('r1', 1, 'uno '), receivedAt: 0 },
      { type: 'reply', reply: token('r1', 1, 'uno '), receivedAt: 0 },
      { type: 'reply', reply: token('old', 2, 'viejo '), receivedAt: 0 },
      { type: 'reply', reply: token('r1', 2, 'dos'), receivedAt: 0 },
    );
    expect(conversation.turns[0]?.text).toBe('uno dos');
  });

  it('ends the turn with the error of the agent', () => {
    const conversation = run(
      asked,
      { type: 'sent', turnId: 't1', requestId: 'r1' },
      { type: 'reply', reply: token('r1', 1, 'a medias'), receivedAt: 0 },
      { type: 'reply', reply: error('r1', 2, true), receivedAt: 0 },
    );
    expect(conversation.turns[0]).toMatchObject({
      status: 'error',
      error: { retryable: true, message: expect.stringContaining('tardó demasiado') as string },
    });
  });

  it('does not turn a finished answer into an error', () => {
    const conversation = run(
      asked,
      { type: 'reply', reply: final('r1', 1, 'Listo'), receivedAt: 0 },
      { type: 'failed', turnId: 't1', message: 'tarde', retryable: true },
    );
    expect(conversation.turns[0]?.status).toBe('done');
  });

  it('a retry replaces the failed turn; a new question keeps it', () => {
    const failed = run(asked, { type: 'failed', turnId: 't1', message: 'x', retryable: true });
    const another = conversationReducer(failed, {
      type: 'asked',
      turnId: 't2',
      question: 'Otra',
      at: 0,
    });
    expect(another.turns.map((turn) => turn.id)).toEqual(['t1', 't2']);
    const retried = conversationReducer(failed, {
      type: 'asked',
      turnId: 't3',
      question: '¿Cómo?',
      at: 0,
      replaces: 't1',
    });
    expect(retried.turns.map((turn) => turn.id)).toEqual(['t3']);
  });
});

describe('countdown', () => {
  it('measures the time to answer with the server dates, not the local clock', () => {
    expect(answerDuration('2026-10-15T12:00:00Z', '2026-10-15T12:02:00Z')).toBe(120_000);

    // The PC clock is far off: the deadline counts from when the accepted reply arrived.
    const conversation = run(asked, {
      type: 'reply',
      reply: accepted('r1', 90),
      receivedAt: 5_000,
    });
    expect(conversation.turns[0]?.deadline).toBe(95_000);
  });

  it('counts whole seconds down to zero', () => {
    expect(secondsLeft(95_000, 5_000)).toBe(90);
    expect(secondsLeft(95_000, 94_200)).toBe(1);
    expect(secondsLeft(95_000, 99_000)).toBe(0);
    expect(formatSeconds(120)).toBe('2:00');
    expect(formatSeconds(65)).toBe('1:05');
    expect(formatSeconds(0)).toBe('0:00');
  });
});
