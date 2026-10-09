import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter } from 'react-router';
import { App } from '../App.tsx';
import { createQueryClient } from '../queryClient.ts';
import { routes } from '../routes.tsx';

/** Renders the whole app at the given path, against the simulated API. */
export function renderApp(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const user = userEvent.setup();
  render(<App router={router} queryClient={createQueryClient()} />);
  return { router, user };
}
