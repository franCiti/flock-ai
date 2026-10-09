import { useState, type SubmitEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router';
import { InvalidCredentialsError } from '../../api/auth.ts';
import markWhite from '../../assets/flock-mark-white.svg';
import styles from './LoginPage.module.css';
import { useLogin, useSession } from './session.ts';

/** Where to go after signing in: the page that asked for a session, or the chat. */
function targetPath(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'from' in state) {
    const from = state.from;
    if (typeof from === 'string' && from.startsWith('/') && from !== '/login') {
      return from;
    }
  }
  return '/chat';
}

function errorMessage(error: Error): string {
  return error instanceof InvalidCredentialsError
    ? 'Usuario o contraseña incorrectos.'
    : 'No se pudo iniciar sesión. Probá de nuevo en unos minutos.';
}

export function LoginPage() {
  const session = useSession();
  const loginMutation = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const target = targetPath(location.state);

  if (session.data) {
    return <Navigate to={target} replace />;
  }

  const handleSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    loginMutation.mutate(
      { username, password },
      {
        onSuccess: () => {
          void navigate(target, { replace: true });
        },
      },
    );
  };

  return (
    <main className={styles.page}>
      <form className={styles.card} onSubmit={handleSubmit} aria-labelledby="login-title">
        <div className={styles.brand}>
          <img src={markWhite} alt="" className={styles.mark} />
          <span>flock-ai</span>
        </div>
        <div className={styles.body}>
          <h1 id="login-title">Iniciar sesión</h1>
          <div className="field">
            <label htmlFor="username">Usuario</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              required
              value={username}
              onChange={(event) => {
                setUsername(event.target.value);
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Contraseña</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
          </div>
          {loginMutation.error && (
            <p role="alert" className={styles.error}>
              {errorMessage(loginMutation.error)}
            </p>
          )}
          <button
            type="submit"
            className="button button-primary"
            disabled={loginMutation.isPending}
          >
            {loginMutation.isPending ? 'Ingresando…' : 'Ingresar'}
          </button>
        </div>
      </form>
    </main>
  );
}
