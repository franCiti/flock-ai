import { screen } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { renderApp } from '../../test/renderApp.tsx';
import { server, mockAuthApi, validCredentials } from '../../test/server.ts';

async function fillAndSubmit(
  user: ReturnType<typeof renderApp>['user'],
  username: string,
  password: string,
) {
  await user.type(await screen.findByLabelText('Usuario'), username);
  await user.type(screen.getByLabelText('Contraseña'), password);
  await user.click(screen.getByRole('button', { name: 'Ingresar' }));
}

describe('login flow', () => {
  it('sends to the login page when there is no session', async () => {
    mockAuthApi();
    const { router } = renderApp('/chat');

    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });

  it('signs in and opens the chat', async () => {
    const { loginBodies } = mockAuthApi();
    const { router, user } = renderApp('/login');

    await fillAndSubmit(user, validCredentials.username, validCredentials.password);

    expect(await screen.findByRole('heading', { name: 'Chat' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/chat');
    expect(screen.getByText(validCredentials.username)).toBeInTheDocument();
    expect(loginBodies).toEqual([validCredentials]);
  });

  it('returns to the page that asked for the session', async () => {
    mockAuthApi();
    const { router, user } = renderApp('/audit');

    await fillAndSubmit(user, validCredentials.username, validCredentials.password);

    expect(await screen.findByRole('heading', { name: 'Auditoría' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/audit');
  });

  it('shows an error for wrong credentials and stays on the login page', async () => {
    mockAuthApi();
    const { router, user } = renderApp('/login');

    await fillAndSubmit(user, validCredentials.username, 'wrong-password');

    expect(await screen.findByRole('alert')).toHaveTextContent('Usuario o contraseña incorrectos.');
    expect(router.state.location.pathname).toBe('/login');
  });

  it('shows a generic error when the server fails', async () => {
    mockAuthApi();
    server.use(http.post('*/api/auth/login', () => new HttpResponse(null, { status: 500 })));
    const { user } = renderApp('/login');

    await fillAndSubmit(user, validCredentials.username, validCredentials.password);

    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo iniciar sesión.');
  });

  it('skips the login page when there is already a session', async () => {
    mockAuthApi({ signedIn: true });
    const { router } = renderApp('/login');

    expect(await screen.findByRole('heading', { name: 'Chat' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/chat');
  });

  it('signs out and goes back to the login page', async () => {
    mockAuthApi({ signedIn: true });
    const { router, user } = renderApp('/chat');

    await user.click(await screen.findByRole('button', { name: 'Cerrar sesión' }));

    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });

  it('offers a retry when the session cannot be checked', async () => {
    mockAuthApi({ signedIn: true });
    server.use(http.get('*/api/auth/me', () => HttpResponse.error(), { once: true }));
    const { user } = renderApp('/chat');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No se pudo conectar con el servidor.',
    );
    await user.click(screen.getByRole('button', { name: 'Reintentar' }));

    expect(await screen.findByRole('heading', { name: 'Chat' })).toBeInTheDocument();
  });
});
