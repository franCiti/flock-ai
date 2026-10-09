import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import styles from './RequireAuth.module.css';
import { useSession } from './session.ts';

/** Shows its children only with a session; otherwise sends the user to the login page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();

  if (session.isPending) {
    return (
      <p role="status" className={styles.message}>
        Cargando…
      </p>
    );
  }
  if (session.isError) {
    return (
      <div role="alert" className={styles.message}>
        <p>No se pudo conectar con el servidor.</p>
        <button
          type="button"
          className="button button-ghost"
          onClick={() => {
            void session.refetch();
          }}
        >
          Reintentar
        </button>
      </div>
    );
  }
  if (session.data === null) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
