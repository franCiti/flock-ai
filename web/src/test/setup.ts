import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { FakeEventSource } from './eventSource.ts';
import { server } from './server.ts';

// jsdom does not lay out pages: scrolling does nothing.
// Some suites run in the node environment, without a DOM.
if (typeof Element !== 'undefined') {
  Element.prototype.scrollIntoView = () => undefined;
}

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
  server.resetHandlers();
});

afterAll(() => {
  server.close();
});
