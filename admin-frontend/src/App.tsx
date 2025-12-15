import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './context/AuthContext';
import { DaemonProvider } from './context/DaemonContext';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { Dashboard } from './pages/Dashboard';
import { Chat } from './pages/Chat';
// Consolidated views
import { MemorySystem } from './pages/MemorySystem';
import { SelfDevelopment } from './pages/SelfDevelopment';
import { Settings } from './pages/Settings';
import { Activity } from './pages/Activity';
// Consolidated: Knowledge (Wiki + Research + Goals)
import { Knowledge } from './pages/Knowledge';
// Remaining standalone views
import { Users } from './pages/Users';
import { UserProfile } from './pages/UserProfile';
import { ConsciousnessHealth } from './pages/ConsciousnessHealth';
import { Metrics } from './pages/Metrics';
import { Projects } from './pages/Projects';
import { Dreams } from './pages/Dreams';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30000,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: '#0a0a0a',
        color: '#666'
      }}>
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Wrap authenticated content with DaemonProvider
  return <DaemonProvider>{children}</DaemonProvider>;
}

// Admin-only route wrapper - redirects non-admins to /chat
function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth();

  if (!isAdmin) {
    return <Navigate to="/chat" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      {/* Public routes */}
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/register"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Register />}
      />

      {/* Protected routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        {/* Dashboard - admin only */}
        <Route index element={<AdminRoute><Dashboard /></AdminRoute>} />

        {/* Non-admin accessible routes */}
        <Route path="chat" element={<Chat />} />
        <Route path="self-development" element={<SelfDevelopment />} />
        <Route path="profile" element={<UserProfile />} />

        {/* Admin-only routes */}
        <Route path="memory" element={<AdminRoute><MemorySystem /></AdminRoute>} />
        <Route path="retrieval" element={<AdminRoute><Navigate to="/memory?tab=retrieval" replace /></AdminRoute>} />
        <Route path="vectors" element={<AdminRoute><Navigate to="/memory?tab=vectors" replace /></AdminRoute>} />
        <Route path="self-model" element={<Navigate to="/self-development?tab=identity" replace />} />
        <Route path="development" element={<Navigate to="/self-development?tab=timeline" replace />} />
        <Route path="activity" element={<AdminRoute><Activity /></AdminRoute>} />
        <Route path="conversations" element={<AdminRoute><Navigate to="/activity?tab=conversations" replace /></AdminRoute>} />
        <Route path="journals" element={<AdminRoute><Navigate to="/activity?tab=journals" replace /></AdminRoute>} />
        <Route path="reflection" element={<AdminRoute><Navigate to="/activity?tab=reflection" replace /></AdminRoute>} />
        <Route path="users" element={<AdminRoute><Users /></AdminRoute>} />
        <Route path="knowledge" element={<AdminRoute><Knowledge /></AdminRoute>} />
        <Route path="wiki" element={<AdminRoute><Navigate to="/knowledge?tab=wiki" replace /></AdminRoute>} />
        <Route path="research" element={<AdminRoute><Navigate to="/knowledge?tab=research" replace /></AdminRoute>} />
        <Route path="goals" element={<AdminRoute><Navigate to="/knowledge?tab=goals" replace /></AdminRoute>} />
        <Route path="settings" element={<AdminRoute><Settings /></AdminRoute>} />
        <Route path="system" element={<AdminRoute><Navigate to="/settings?tab=health" replace /></AdminRoute>} />
        <Route path="data" element={<AdminRoute><Navigate to="/settings?tab=export" replace /></AdminRoute>} />
        <Route path="consciousness" element={<AdminRoute><ConsciousnessHealth /></AdminRoute>} />
        <Route path="dreams" element={<AdminRoute><Dreams /></AdminRoute>} />
        <Route path="metrics" element={<AdminRoute><Metrics /></AdminRoute>} />
        <Route path="projects" element={<AdminRoute><Projects /></AdminRoute>} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
