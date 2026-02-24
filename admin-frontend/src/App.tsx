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
// Knowledge hub + promoted standalone pages
import { Knowledge } from './pages/Knowledge';
import { Research } from './pages/Research';
import { Wiki } from './pages/Wiki';
import { Goals } from './pages/Goals';
// Remaining standalone views
import { Users } from './pages/Users';
import { UserProfile } from './pages/UserProfile';
// ConsciousnessHealth now embedded in Mind page
import { Metrics } from './pages/Metrics';
import { Projects } from './pages/Projects';
import { Dreams } from './pages/Dreams';
import { Feedback } from './pages/Feedback';
import { GenesisDream } from './pages/GenesisDream';
import { Homepage } from './pages/Homepage';
import { Architecture } from './pages/Architecture';
import { Wonderland } from './pages/Wonderland';
import { PeopleDex } from './pages/PeopleDex';
import { News } from './pages/News';
// Thymos now embedded in Mind page
import { Mind } from './pages/Mind';
import { Agency } from './pages/Agency';
import { Gallery } from './pages/Gallery';
import { ArtStudy } from './pages/ArtStudy';
import { Grimoire } from './pages/Grimoire';
import { Music } from './pages/Music';
import { DailyActivity } from './pages/DailyActivity';
import { VoiceCall } from './pages/VoiceCall';
import { VoiceEnrollment } from './pages/VoiceEnrollment';
import { FaceEnrollment } from './pages/FaceEnrollment';
import { Email } from './pages/Email';

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
        <Route path="feedback" element={<Feedback />} />
        <Route path="genesis" element={<GenesisDream />} />

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
        <Route path="wiki" element={<AdminRoute><Wiki /></AdminRoute>} />
        <Route path="research" element={<AdminRoute><Research /></AdminRoute>} />
        <Route path="goals" element={<AdminRoute><Goals /></AdminRoute>} />
        <Route path="settings" element={<AdminRoute><Settings /></AdminRoute>} />
        <Route path="email" element={<AdminRoute><Email /></AdminRoute>} />
        <Route path="system" element={<AdminRoute><Navigate to="/settings?tab=health" replace /></AdminRoute>} />
        <Route path="data" element={<AdminRoute><Navigate to="/settings?tab=export" replace /></AdminRoute>} />
        <Route path="consciousness" element={<AdminRoute><Navigate to="/mind?tab=consciousness" replace /></AdminRoute>} />
        <Route path="dreams" element={<AdminRoute><Dreams /></AdminRoute>} />
        <Route path="metrics" element={<AdminRoute><Metrics /></AdminRoute>} />
        <Route path="projects" element={<AdminRoute><Projects /></AdminRoute>} />
        <Route path="homepage" element={<AdminRoute><Homepage /></AdminRoute>} />
        <Route path="architecture" element={<AdminRoute><Architecture /></AdminRoute>} />
        <Route path="wonderland" element={<AdminRoute><Wonderland /></AdminRoute>} />
        <Route path="peopledex" element={<AdminRoute><PeopleDex /></AdminRoute>} />
        <Route path="news" element={<AdminRoute><News /></AdminRoute>} />
        {/* Mind hub - unified emotional/cognitive state */}
        <Route path="mind" element={<AdminRoute><Mind /></AdminRoute>} />
        {/* Legacy routes redirect to Mind tabs */}
        <Route path="thymos" element={<AdminRoute><Navigate to="/mind?tab=thymos" replace /></AdminRoute>} />
        {/* Agency - autonomous goal formation and outreach */}
        <Route path="agency" element={<AdminRoute><Agency /></AdminRoute>} />
        <Route path="gallery" element={<AdminRoute><Gallery /></AdminRoute>} />
        <Route path="music" element={<AdminRoute><Music /></AdminRoute>} />
        <Route path="art-study" element={<AdminRoute><ArtStudy /></AdminRoute>} />
        <Route path="grimoire" element={<AdminRoute><Grimoire /></AdminRoute>} />
        <Route path="daily-activity" element={<AdminRoute><DailyActivity /></AdminRoute>} />
        <Route path="voice" element={<AdminRoute><VoiceCall /></AdminRoute>} />
        <Route path="voice-enrollment" element={<AdminRoute><VoiceEnrollment /></AdminRoute>} />
        <Route path="face-enrollment" element={<AdminRoute><FaceEnrollment /></AdminRoute>} />
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
