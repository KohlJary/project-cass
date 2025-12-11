import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
// Consolidated views
import { MemorySystem } from './pages/MemorySystem';
import { SelfDevelopment } from './pages/SelfDevelopment';
import { Settings } from './pages/Settings';
import { Activity } from './pages/Activity';
// Legacy imports (to be consolidated)
import { Users } from './pages/Users';
// Journals consolidated into Activity
// Conversations consolidated into Activity
// SelfModel consolidated into SelfDevelopment
// System consolidated into Settings
import { Wiki } from './pages/Wiki';
import { Research } from './pages/Research';
// DataManagement consolidated into Settings
// Development consolidated into SelfDevelopment
import { ConsciousnessHealth } from './pages/ConsciousnessHealth';
// SoloReflection consolidated into Activity
import Goals from './pages/Goals';
import { Metrics } from './pages/Metrics';
import { Projects } from './pages/Projects';

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

  return <>{children}</>;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        {/* Consolidated: Memory System (Memory + Retrieval + Vectors) */}
        <Route path="memory" element={<MemorySystem />} />
        {/* Redirects for old routes */}
        <Route path="retrieval" element={<Navigate to="/memory?tab=retrieval" replace />} />
        <Route path="vectors" element={<Navigate to="/memory?tab=vectors" replace />} />
        {/* Consolidated: Self-Development (Self-Model + Development) */}
        <Route path="self-development" element={<SelfDevelopment />} />
        {/* Redirects for old routes */}
        <Route path="self-model" element={<Navigate to="/self-development?tab=identity" replace />} />
        <Route path="development" element={<Navigate to="/self-development?tab=timeline" replace />} />
        {/* Consolidated: Activity (Conversations + Journals + Reflection) */}
        <Route path="activity" element={<Activity />} />
        {/* Redirects for old routes */}
        <Route path="conversations" element={<Navigate to="/activity?tab=conversations" replace />} />
        <Route path="journals" element={<Navigate to="/activity?tab=journals" replace />} />
        <Route path="reflection" element={<Navigate to="/activity?tab=reflection" replace />} />
        {/* Remaining views */}
        <Route path="users" element={<Users />} />
        <Route path="wiki" element={<Wiki />} />
        <Route path="research" element={<Research />} />
        {/* Consolidated: Settings (System + Data) */}
        <Route path="settings" element={<Settings />} />
        {/* Redirects for old routes */}
        <Route path="system" element={<Navigate to="/settings?tab=health" replace />} />
        <Route path="data" element={<Navigate to="/settings?tab=export" replace />} />
        <Route path="consciousness" element={<ConsciousnessHealth />} />
        <Route path="goals" element={<Goals />} />
        <Route path="metrics" element={<Metrics />} />
        <Route path="projects" element={<Projects />} />
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
