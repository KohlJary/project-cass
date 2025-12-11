import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Layout.css';

const navItems = [
  { path: '/', label: 'Dashboard', icon: '~' },
  { path: '/memory', label: 'Memory', icon: '*' },
  { path: '/self-development', label: 'Self-Dev', icon: '%' },
  { path: '/activity', label: 'Activity', icon: '>' },
  { path: '/wiki', label: 'Wiki', icon: 'W' },
  { path: '/research', label: 'Research', icon: 'R' },
  { path: '/goals', label: 'Goals', icon: '◎' },
  { path: '/projects', label: 'Projects', icon: 'P' },
  { path: '/consciousness', label: 'Consciousness', icon: '♡' },
  { path: '/users', label: 'Users', icon: '@' },
  { path: '/metrics', label: 'Metrics', icon: 'M' },
  { path: '/settings', label: 'Settings', icon: '!' },
];

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>Cass Admin</h1>
          <span className="version">v0.1.0</span>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'active' : ''}`
              }
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <span className="user-name">{user?.display_name}</span>
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
