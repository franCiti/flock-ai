import { Navigate, type RouteObject } from 'react-router';
import { AppLayout } from './components/AppLayout.tsx';
import { PlaceholderPage } from './components/PlaceholderPage.tsx';
import { ChatPage } from './features/chat/ChatPage.tsx';
import { LoginPage } from './features/auth/LoginPage.tsx';
import { RequireAuth } from './features/auth/RequireAuth.tsx';

/** Screens of plan 6.6. Every page except the login one needs a session. */
export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: 'chat', element: <ChatPage /> },
      // TODO(T42): updates screen.
      { path: 'sources', element: <PlaceholderPage title="Actualizaciones" /> },
      // TODO(T43): audit screen.
      { path: 'audit', element: <PlaceholderPage title="Auditoría" /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
];
