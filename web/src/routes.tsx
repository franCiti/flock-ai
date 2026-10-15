import { Navigate, type RouteObject } from 'react-router';
import { AppLayout } from './components/AppLayout.tsx';
import { ChatPage } from './features/chat/ChatPage.tsx';
import { AuditPage } from './features/audit/AuditPage.tsx';
import { LoginPage } from './features/auth/LoginPage.tsx';
import { RequireAuth } from './features/auth/RequireAuth.tsx';
import { UpdatesPage } from './features/updates/UpdatesPage.tsx';

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
      { path: 'sources', element: <UpdatesPage /> },
      { path: 'audit', element: <AuditPage /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
];
