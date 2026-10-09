import { NavLink, Outlet, useNavigate } from 'react-router';
import markWhite from '../assets/flock-mark-white.svg';
import { useLogout, useSession } from '../features/auth/session.ts';
import styles from './AppLayout.module.css';

const sections = [
  { path: '/chat', label: 'Chat' },
  { path: '/sources', label: 'Actualizaciones' },
  { path: '/audit', label: 'Auditoría' },
] as const;

/** Frame of the signed-in pages: dark brand sidebar (design system, section 7) and content. */
export function AppLayout() {
  const session = useSession();
  const logout = useLogout();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout.mutate(undefined, {
      onSettled: () => {
        void navigate('/login', { replace: true });
      },
    });
  };

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <img src={markWhite} alt="" className={styles.mark} />
          <span>flock-ai</span>
        </div>
        <nav aria-label="Secciones" className={styles.nav}>
          {sections.map((section) => (
            <NavLink
              key={section.path}
              to={section.path}
              className={({ isActive }) =>
                isActive ? `${styles.link ?? ''} ${styles.active ?? ''}` : styles.link
              }
            >
              {section.label}
            </NavLink>
          ))}
        </nav>
        <div className={styles.user}>
          <span className={styles.username}>{session.data?.username}</span>
          <button
            type="button"
            className="button button-light"
            onClick={handleLogout}
            disabled={logout.isPending}
          >
            Cerrar sesión
          </button>
        </div>
      </aside>
      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  );
}
