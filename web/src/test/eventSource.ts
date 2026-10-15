import { act } from '@testing-library/react';
import type { AgentReply } from '../api/chat.ts';

type Listener = (event: MessageEvent<string>) => void;

/**
 * Stands in for the browser's EventSource (jsdom has none): tests push the replies of the agent
 * with {@link FakeEventSource.emit}.
 */
export class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  /** Every stream opened since the test started, oldest first. */
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.OPEN;
  private readonly listeners = new Map<string, Listener[]>();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  /** The stream the page has open now. */
  static current(): FakeEventSource {
    const source = FakeEventSource.instances.at(-1);
    if (source === undefined) {
      throw new Error('No EventSource was opened');
    }
    return source;
  }

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close(): void {
    this.readyState = FakeEventSource.CLOSED;
  }

  /** Delivers a reply as the Core API does: event name = type, data = the message. */
  emit(reply: AgentReply): void {
    const event = new MessageEvent('message', { data: JSON.stringify(reply) });
    act(() => {
      for (const listener of this.listeners.get(reply.type) ?? []) {
        listener(event);
      }
    });
  }

  /** The browser gave up reconnecting (for example, a 401). */
  fail(): void {
    this.readyState = FakeEventSource.CLOSED;
    act(() => {
      for (const listener of this.listeners.get('error') ?? []) {
        listener(new MessageEvent('error'));
      }
    });
  }
}
