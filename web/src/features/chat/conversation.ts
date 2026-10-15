import type { AgentReply, FinalReply } from '../../api/chat.ts';

/** A question and what came back for it (plan 6.6). */
export interface Turn {
  id: string;
  question: string;
  /** Known when the Core API answers the POST, or with the first reply, whichever comes first. */
  requestId?: string;
  status: 'waiting' | 'streaming' | 'done' | 'error';
  /** The answer so far: the tokens, replaced by the final answer when it arrives. */
  text: string;
  lastSeq: number;
  /** When the agent stops trying, on the local clock (ms). Known with the accepted reply. */
  deadline?: number;
  /** When the question was sent, on the local clock (ms). */
  sentAt: number;
  final?: FinalReply;
  error?: { message: string; retryable: boolean };
}

export interface Conversation {
  id: string;
  turns: Turn[];
}

export type ConversationAction =
  /** {@code replaces}: the failed turn that is being retried. */
  | { type: 'asked'; turnId: string; question: string; at: number; replaces?: string | undefined }
  | { type: 'sent'; turnId: string; requestId: string }
  | { type: 'failed'; turnId: string; message: string; retryable: boolean }
  | { type: 'reply'; reply: AgentReply; receivedAt: number }
  | { type: 'reset'; conversationId: string };

export const messages = {
  sendFailed: 'No se pudo enviar la pregunta. Probá de nuevo.',
  noAnswer: 'La respuesta tardó demasiado. Probá de nuevo.',
  notAccepted: 'El asistente no está disponible en este momento. Probá de nuevo en unos minutos.',
};

export function newConversation(id: string): Conversation {
  return { id, turns: [] };
}

/** The turn still waiting for its answer, if any: only one at a time. */
export function pendingTurn(conversation: Conversation): Turn | undefined {
  const last = conversation.turns.at(-1);
  return last !== undefined && (last.status === 'waiting' || last.status === 'streaming')
    ? last
    : undefined;
}

export function conversationReducer(
  conversation: Conversation,
  action: ConversationAction,
): Conversation {
  switch (action.type) {
    case 'reset':
      return newConversation(action.conversationId);
    case 'asked':
      return {
        ...conversation,
        turns: [
          ...conversation.turns.filter((turn) => turn.id !== action.replaces),
          {
            id: action.turnId,
            question: action.question,
            status: 'waiting',
            text: '',
            lastSeq: -1,
            sentAt: action.at,
          },
        ],
      };
    case 'sent':
      return updateTurn(conversation, action.turnId, (turn) =>
        turn.requestId === undefined ? { ...turn, requestId: action.requestId } : turn,
      );
    case 'failed':
      return updateTurn(conversation, action.turnId, (turn) =>
        turn.status === 'done' || turn.status === 'error'
          ? turn
          : {
              ...turn,
              status: 'error',
              error: { message: action.message, retryable: action.retryable },
            },
      );
    case 'reply': {
      const turn = pendingTurn(conversation);
      if (turn === undefined) {
        return conversation;
      }
      return updateTurn(conversation, turn.id, (current) =>
        applyReply(current, action.reply, action.receivedAt),
      );
    }
  }
}

/** Adds a reply of the agent to its turn; replies of other requests or repeated ones change nothing. */
export function applyReply(turn: Turn, reply: AgentReply, receivedAt: number): Turn {
  if (
    reply.requestId === null ||
    (turn.requestId !== undefined && turn.requestId !== reply.requestId)
  ) {
    return turn;
  }
  if (reply.seq <= turn.lastSeq) {
    return turn;
  }
  const base = { ...turn, requestId: reply.requestId, lastSeq: reply.seq };
  switch (reply.type) {
    case 'accepted':
      return { ...base, deadline: receivedAt + answerDuration(reply.sentAt, reply.deadlineAt) };
    case 'token':
      return { ...base, status: 'streaming', text: turn.text + reply.text };
    case 'final':
      return { ...base, status: 'done', text: reply.answer, final: reply };
    case 'error':
      return {
        ...base,
        status: 'error',
        error: { message: reply.message, retryable: reply.retryable },
      };
  }
}

/**
 * How long the agent has to answer: deadlineAt − sentAt, both from the server, so the clock of the
 * PC does not matter (plan 6.6).
 */
export function answerDuration(sentAt: string, deadlineAt: string): number {
  return Math.max(0, Date.parse(deadlineAt) - Date.parse(sentAt));
}

/** Whole seconds left until the deadline, never negative. */
export function secondsLeft(deadline: number, now: number): number {
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

/** "1:05" */
export function formatSeconds(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes)}:${String(seconds % 60).padStart(2, '0')}`;
}

function updateTurn(
  conversation: Conversation,
  turnId: string,
  update: (turn: Turn) => Turn,
): Conversation {
  return {
    ...conversation,
    turns: conversation.turns.map((turn) => (turn.id === turnId ? update(turn) : turn)),
  };
}
