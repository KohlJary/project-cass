import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Memory } from './pages/Memory';
import { Users } from './pages/Users';
import { Journals } from './pages/Journals';
import { Conversations } from './pages/Conversations';
import { Retrieval } from './pages/Retrieval';
import { SelfModel } from './pages/SelfModel';
import { System } from './pages/System';
import { Vectors } from './pages/Vectors';
import { Wiki } from './pages/Wiki';
import { Research } from './pages/Research';
import { DataManagement } from './pages/DataManagement';
import { Development } from './pages/Development';
import { ConsciousnessHealth } from './pages/ConsciousnessHealth';
import { SoloReflection } from './pages/SoloReflection';
import Goals from './pages/Goals';

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
        <Route path="memory" element={<Memory />} />
        <Route path="users" element={<Users />} />
        <Route path="journals" element={<Journals />} />
        <Route path="conversations" element={<Conversations />} />
        <Route path="retrieval" element={<Retrieval />} />
        <Route path="wiki" element={<Wiki />} />
        <Route path="research" element={<Research />} />
        <Route path="system" element={<System />} />
        <Route path="vectors" element={<Vectors />} />
        <Route path="self-model" element={<SelfModel />} />
        <Route path="development" element={<Development />} />
        <Route path="data" element={<DataManagement />} />
        <Route path="consciousness" element={<ConsciousnessHealth />} />
        <Route path="reflection" element={<SoloReflection />} />
        <Route path="goals" element={<Goals />} />
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
