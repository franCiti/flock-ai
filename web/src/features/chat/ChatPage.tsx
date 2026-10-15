import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type ReactNode,
  type SyntheticEvent,
} from 'react';
import { Link } from 'react-router';
import { fetchConfig, fetchPersonas, openReplyStream, sendQuestion } from '../../api/chat.ts';
import { ApiError } from '../../api/client.ts';
import { citationLinks } from './citationLinks.ts';
import { Citations } from './Citations.tsx';
import {
  conversationReducer,
  messages,
  newConversation,
  pendingTurn,
  type Turn,
} from './conversation.ts';
import { Countdown } from './Countdown.tsx';
import { SafeMarkdown } from './SafeMarkdown.tsx';
import styles from './ChatPage.module.css';

/** Without an accepted reply by then, the agent is not taking requests. */
export const ACCEPT_TIMEOUT_MS = 30_000;
/** After the deadline the agent sends a timeout error; this covers it getting lost. */
export const DEADLINE_GRACE_MS = 15_000;

/** The chat with a virtual persona (spec HU6, HU10, plan 6.6). */
export function ChatPage() {
  const queryClient = useQueryClient();
  const personas = useQuery({ queryKey: ['personas'], queryFn: fetchPersonas });
  const config = useQuery({ queryKey: ['config'], queryFn: fetchConfig });

  const [selectedPersona, setSelectedPersona] = useState<string>();
  const [conversation, dispatch] = useReducer(conversationReducer, undefined, () =>
    newConversation(crypto.randomUUID()),
  );
  const [question, setQuestion] = useState('');
  const [streamClosed, setStreamClosed] = useState(false);
  const [streamGeneration, setStreamGeneration] = useState(0);
  const endRef = useRef<HTMLDivElement>(null);

  const personaId = selectedPersona ?? personas.data?.[0]?.id;
  const maxChars = config.data?.maxQuestionChars;
  const pending = pendingTurn(conversation);

  // The stream opens before the first question, so no reply is missed (plan 6.4).
  useEffect(() => {
    const stream = openReplyStream(conversation.id, {
      onReply: (reply) => {
        dispatch({ type: 'reply', reply, receivedAt: Date.now() });
      },
      onClosed: () => {
        setStreamClosed(true);
        // Usually the session ended: checking it sends to the login page if so.
        void queryClient.invalidateQueries({ queryKey: ['session'] });
      },
    });
    return () => {
      stream.close();
    };
  }, [conversation.id, streamGeneration, queryClient]);

  // A question that gets no accepted reply, or no answer after its deadline, ends with an error.
  useEffect(() => {
    if (pending === undefined) {
      return;
    }
    const limit =
      pending.deadline === undefined
        ? { at: pending.sentAt + ACCEPT_TIMEOUT_MS, message: messages.notAccepted }
        : { at: pending.deadline + DEADLINE_GRACE_MS, message: messages.noAnswer };
    const timer = setTimeout(
      () => {
        dispatch({ type: 'failed', turnId: pending.id, message: limit.message, retryable: true });
      },
      Math.max(0, limit.at - Date.now()),
    );
    return () => {
      clearTimeout(timer);
    };
  }, [pending]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [conversation.turns]);

  const ask = useCallback(
    (text: string, replaces?: string) => {
      if (personaId === undefined) {
        return;
      }
      const turnId = crypto.randomUUID();
      dispatch({ type: 'asked', turnId, question: text, at: Date.now(), replaces });
      sendQuestion(conversation.id, personaId, text).then(
        (requestId) => {
          dispatch({ type: 'sent', turnId, requestId });
        },
        (error: unknown) => {
          if (error instanceof ApiError && error.status === 401) {
            void queryClient.invalidateQueries({ queryKey: ['session'] });
          }
          dispatch({ type: 'failed', turnId, message: messages.sendFailed, retryable: true });
        },
      );
    },
    [conversation.id, personaId, queryClient],
  );

  const startNewConversation = (nextPersona?: string) => {
    if (nextPersona !== undefined) {
      setSelectedPersona(nextPersona);
    }
    setStreamClosed(false);
    dispatch({ type: 'reset', conversationId: crypto.randomUUID() });
  };

  const trimmed = question.trim();
  const tooLong = maxChars !== undefined && question.length > maxChars;
  const canSend = trimmed !== '' && !tooLong && pending === undefined && personaId !== undefined;

  const handleSubmit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (!canSend) {
      return;
    }
    ask(trimmed);
    setQuestion('');
  };

  if (personas.isPending || config.isPending) {
    return (
      <ChatFrame>
        <p className={styles.muted}>Cargando…</p>
      </ChatFrame>
    );
  }
  if (personas.isError || config.isError) {
    return (
      <ChatFrame>
        <p role="alert" className={styles.alert}>
          No se pudo cargar el chat. Probá recargar la página.
        </p>
      </ChatFrame>
    );
  }
  if (personas.data.length === 0) {
    return (
      <ChatFrame>
        <p className={styles.hint}>
          Todavía no hay personas virtuales. Cargá su conocimiento desde{' '}
          <Link to="/sources">Actualizaciones</Link>.
        </p>
      </ChatFrame>
    );
  }

  const personaName = (id: string) =>
    personas.data.find((persona) => persona.id === id)?.displayName ?? id;

  return (
    <section className={styles.page} aria-labelledby="page-title">
      <header className={styles.header}>
        <h1 id="page-title">Chat</h1>
        <div className={styles.field}>
          <label htmlFor="persona">Persona</label>
          <select
            id="persona"
            value={personaId}
            disabled={pending !== undefined}
            onChange={(event) => {
              // Each conversation is with one persona.
              startNewConversation(event.target.value);
            }}
          >
            {personas.data.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {persona.displayName}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="button button-ghost"
          onClick={() => {
            startNewConversation();
          }}
          disabled={conversation.turns.length === 0}
        >
          Conversación nueva
        </button>
      </header>

      {streamClosed ? (
        <div role="alert" className={styles.alert}>
          Se perdió la conexión con el servidor.{' '}
          <button
            type="button"
            className="button button-ghost"
            onClick={() => {
              setStreamClosed(false);
              setStreamGeneration((generation) => generation + 1);
            }}
          >
            Reconectar
          </button>
        </div>
      ) : null}

      <ol className={styles.turns} aria-label="Conversación">
        {conversation.turns.length === 0 ? (
          <li className={styles.hint}>
            Preguntale algo a {personaId === undefined ? '' : personaName(personaId)}.
          </li>
        ) : null}
        {conversation.turns.map((turn) => (
          <TurnView
            key={turn.id}
            turn={turn}
            onRetry={() => {
              ask(turn.question, turn.id);
            }}
            onReferral={(id) => {
              startNewConversation(id);
            }}
            knownPersona={(id) => personas.data.some((persona) => persona.id === id)}
          />
        ))}
      </ol>
      <div ref={endRef} />

      <form className={styles.composer} onSubmit={handleSubmit}>
        <label htmlFor="question" className={styles.srOnly}>
          Pregunta
        </label>
        <textarea
          id="question"
          value={question}
          rows={3}
          placeholder="Escribí tu pregunta…"
          onChange={(event) => {
            setQuestion(event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              handleSubmit(event);
            }
          }}
        />
        <div className={styles.composerFoot}>
          <span
            className={
              tooLong ? `${styles.counter ?? ''} ${styles.counterOver ?? ''}` : styles.counter
            }
            aria-live="polite"
          >
            {question.length} / {maxChars}
          </span>
          <button type="submit" className="button button-primary" disabled={!canSend}>
            Enviar
          </button>
        </div>
      </form>
    </section>
  );
}

/** The screen with its title, while there is nothing to chat about yet. */
function ChatFrame({ children }: { children: ReactNode }) {
  return (
    <section className={styles.page} aria-labelledby="page-title">
      <h1 id="page-title">Chat</h1>
      {children}
    </section>
  );
}

function TurnView({
  turn,
  onRetry,
  onReferral,
  knownPersona,
}: {
  turn: Turn;
  onRetry: () => void;
  onReferral: (personaId: string) => void;
  knownPersona: (personaId: string) => boolean;
}) {
  const referral = turn.final?.referral;
  return (
    <li className={styles.turn}>
      <p className={styles.question}>{turn.question}</p>
      <article
        className={styles.answer}
        aria-busy={turn.status === 'waiting' || turn.status === 'streaming'}
      >
        {turn.status === 'waiting' || turn.status === 'streaming' ? (
          <div className={styles.status}>
            <span>{turn.status === 'waiting' ? 'Buscando la respuesta…' : 'Respondiendo…'}</span>
            {turn.deadline === undefined ? null : <Countdown deadline={turn.deadline} />}
          </div>
        ) : null}
        {turn.text === '' ? null : (
          <div className={styles.markdown}>
            <SafeMarkdown text={turn.text} links={citationLinks(turn.final?.citations ?? [])} />
          </div>
        )}
        {turn.final === undefined ? null : <Citations citations={turn.final.citations} />}
        {referral ? (
          <div className={styles.referral}>
            <span>
              Preguntale a <strong>{referral.displayName}</strong>
            </span>
            {knownPersona(referral.id) ? (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => {
                  onReferral(referral.id);
                }}
              >
                Conversar con {referral.displayName}
              </button>
            ) : null}
          </div>
        ) : null}
        {turn.error === undefined ? null : (
          <div role="alert" className={styles.alert}>
            <span>{turn.error.message}</span>
            {turn.error.retryable ? (
              <button type="button" className="button button-ghost" onClick={onRetry}>
                Reintentar
              </button>
            ) : null}
          </div>
        )}
      </article>
    </li>
  );
}
