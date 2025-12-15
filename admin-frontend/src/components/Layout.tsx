import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useDaemon } from '../context/DaemonContext';
import './Layout.css';

// Nav items available to all authenticated users
const userNavItems = [
  { path: '/chat', label: 'Chat', icon: 'C' },
  { path: '/self-development', label: 'Self-Dev', icon: '%' },
  { path: '/profile', label: 'My Profile', icon: '@' },
];

// Nav items only available to admins
const adminNavItems = [
  { path: '/', label: 'Dashboard', icon: '~' },
  { path: '/chat', label: 'Chat', icon: 'C' },
  { path: '/memory', label: 'Memory', icon: '*' },
  { path: '/self-development', label: 'Self-Dev', icon: '%' },
  { path: '/activity', label: 'Activity', icon: '>' },
  { path: '/knowledge', label: 'Knowledge', icon: 'K' },
  { path: '/projects', label: 'Projects', icon: 'P' },
  { path: '/consciousness', label: 'Consciousness', icon: '♡' },
  { path: '/dreams', label: 'Dreams', icon: 'D' },
  { path: '/users', label: 'Users', icon: '@' },
  { path: '/metrics', label: 'Metrics', icon: 'M' },
  { path: '/settings', label: 'Settings', icon: '!' },
];

export function Layout() {
  const { user, logout, isAdmin } = useAuth();
  const { currentDaemon, availableDaemons, isLoading: daemonLoading, setDaemon } = useDaemon();

  // Use appropriate nav items based on role
  const navItems = isAdmin ? adminNavItems : userNavItems;

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>Cass Admin</h1>
          {isAdmin && (
            <div className="daemon-selector">
              {daemonLoading ? (
                <span className="daemon-loading">Loading...</span>
              ) : availableDaemons.length > 1 ? (
                <select
                  value={currentDaemon?.id || ''}
                  onChange={(e) => setDaemon(e.target.value)}
                  className="daemon-select"
                >
                  {availableDaemons.map((daemon) => (
                    <option key={daemon.id} value={daemon.id}>
                      {daemon.label} ({daemon.name})
                    </option>
                  ))}
                </select>
              ) : (
                <span className="daemon-name">{currentDaemon?.label || currentDaemon?.name || 'No daemon'}</span>
              )}
            </div>
          )}
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'active' : ''}`
              }
              end={item.path === '/'}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <span className="user-name">{user?.display_name}</span>
            {isAdmin && <span className="admin-badge">Admin</span>}
            <button className="logout-btn" onClick={logout}>
              Logout
            </button>
          </div>
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
