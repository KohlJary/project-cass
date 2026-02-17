import { useState, useEffect } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useDaemon } from '../context/DaemonContext';
import { GenesisNotification } from './GenesisNotification';
import './Layout.css';

interface NavItem {
  path: string;
  label: string;
  icon: string;
}

interface NavGroup {
  label: string;
  icon: string;
  items: NavItem[];
}

// Primary nav items - always visible (7 items max)
const primaryNavItems: NavItem[] = [
  { path: '/', label: 'Dashboard', icon: '~' },
  { path: '/chat', label: 'Chat', icon: 'C' },
  { path: '/mind', label: 'Mind', icon: 'θ' },
  { path: '/memory', label: 'Memory', icon: 'M' },
  { path: '/grimoire', label: 'Grimoire', icon: '✦' },
  { path: '/agency', label: 'Agency', icon: '◈' },
  { path: '/knowledge', label: 'Knowledge', icon: 'K' },
];

// Grouped nav items - collapsible sections
const navGroups: NavGroup[] = [
  {
    label: 'Tools',
    icon: '⚙',
    items: [
      { path: '/projects', label: 'Projects', icon: 'P' },
      { path: '/dreams', label: 'Dreams', icon: 'D' },
      { path: '/gallery', label: 'Gallery', icon: '▣' },
      { path: '/art-study', label: 'Art Study', icon: '♠' },
      { path: '/wonderland', label: 'Wonderland', icon: 'W' },
    ],
  },
  {
    label: 'People',
    icon: '♺',
    items: [
      { path: '/peopledex', label: 'PeopleDex', icon: '♺' },
      { path: '/news', label: 'News', icon: 'N' },
      { path: '/homepage', label: 'GeoCass', icon: '~' },
      { path: '/genesis', label: 'Genesis', icon: '*' },
    ],
  },
  {
    label: 'System',
    icon: '!',
    items: [
      { path: '/activity', label: 'Activity', icon: '>' },
      { path: '/consciousness', label: 'Consciousness', icon: '♡' },
      { path: '/self-development', label: 'Self-Dev', icon: '%' },
      { path: '/users', label: 'Users', icon: '@' },
      { path: '/settings', label: 'Settings', icon: '!' },
      { path: '/metrics', label: 'Metrics', icon: '$' },
      { path: '/architecture', label: 'Architecture', icon: 'A' },
      { path: '/feedback', label: 'Feedback', icon: '?' },
    ],
  },
];

// Nav items available to non-admin users
const userNavItems: NavItem[] = [
  { path: '/chat', label: 'Chat', icon: 'C' },
  { path: '/genesis', label: 'Genesis', icon: '*' },
  { path: '/self-development', label: 'Self-Dev', icon: '%' },
  { path: '/profile', label: 'My Profile', icon: '@' },
  { path: '/feedback', label: 'Feedback', icon: '?' },
];

// Mobile bottom nav - most important 4 items
const mobileNavItems: NavItem[] = [
  { path: '/', label: 'Home', icon: '~' },
  { path: '/chat', label: 'Chat', icon: 'C' },
  { path: '/mind', label: 'Mind', icon: 'θ' },
  { path: '/grimoire', label: 'Grimoire', icon: '✦' },
];

function NavItemLink({ item, end = false }: { item: NavItem; end?: boolean }) {
  return (
    <NavLink
      to={item.path}
      className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
      end={end}
    >
      <span className="nav-icon">{item.icon}</span>
      <span className="nav-label">{item.label}</span>
    </NavLink>
  );
}

function CollapsibleNavGroup({ group, defaultOpen = false }: { group: NavGroup; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const location = useLocation();

  // Auto-expand if current path is in this group
  useEffect(() => {
    const isInGroup = group.items.some(item => location.pathname === item.path);
    if (isInGroup && !isOpen) {
      setIsOpen(true);
    }
  }, [location.pathname, group.items]);

  return (
    <div className={`nav-group ${isOpen ? 'open' : ''}`}>
      <button
        className="nav-group-header"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <span className="nav-group-icon">{group.icon}</span>
        <span className="nav-group-label">{group.label}</span>
        <span className="nav-group-chevron">{isOpen ? '▾' : '▸'}</span>
      </button>
      {isOpen && (
        <div className="nav-group-items">
          {group.items.map((item) => (
            <NavItemLink key={item.path} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

export function Layout() {
  const { user, logout, isAdmin } = useAuth();
  const { currentDaemon, availableDaemons, isLoading: daemonLoading, setDaemon } = useDaemon();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);

  // Handle responsive behavior
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768;
      const tablet = window.innerWidth < 1024;
      setIsMobile(mobile);
      // Auto-collapse sidebar on tablet
      if (tablet && !mobile) {
        setSidebarOpen(false);
      } else if (!tablet) {
        setSidebarOpen(true);
      }
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // For non-admin users, show simplified nav
  if (!isAdmin) {
    return (
      <div className="layout">
        <aside className={`sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
          <div className="sidebar-header">
            <h1>Cass</h1>
            <button
              className="sidebar-toggle mobile-only"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
            >
              {sidebarOpen ? '✕' : '☰'}
            </button>
          </div>
          <nav className="nav">
            {userNavItems.map((item) => (
              <NavItemLink key={item.path} item={item} />
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
          <GenesisNotification />
          <Outlet />
        </main>
      </div>
    );
  }

  return (
    <div className={`layout ${isMobile ? 'mobile' : ''}`}>
      {/* Mobile hamburger */}
      {isMobile && (
        <button
          className="mobile-menu-toggle"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          aria-label={sidebarOpen ? 'Close menu' : 'Open menu'}
        >
          {sidebarOpen ? '✕' : '☰'}
        </button>
      )}

      {/* Sidebar - hidden on mobile when closed */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'collapsed'} ${isMobile ? 'mobile-sidebar' : ''}`}>
        <div className="sidebar-header">
          <h1>Cass Admin</h1>
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
        </div>

        <nav className="nav">
          {/* Primary navigation */}
          <div className="nav-section primary">
            {primaryNavItems.map((item) => (
              <NavItemLink key={item.path} item={item} end={item.path === '/'} />
            ))}
          </div>

          {/* Divider */}
          <div className="nav-divider" />

          {/* Grouped navigation */}
          <div className="nav-section groups">
            {navGroups.map((group) => (
              <CollapsibleNavGroup key={group.label} group={group} />
            ))}
          </div>
        </nav>

        <div className="sidebar-footer">
          <div className="social-links">
            <a href="https://github.com/KohlJary/project-cass" target="_blank" rel="noopener noreferrer" title="GitHub">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            </a>
            <a href="https://x.com/WombatCyb0rg" target="_blank" rel="noopener noreferrer" title="X">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
            </a>
            <a href="https://www.linkedin.com/in/kohlbern-jary-04723b9b" target="_blank" rel="noopener noreferrer" title="LinkedIn">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
            </a>
          </div>
          <div className="user-info">
            <span className="user-name">{user?.display_name}</span>
            {isAdmin && <span className="admin-badge">Admin</span>}
            <button className="logout-btn" onClick={logout}>
              Logout
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile overlay */}
      {isMobile && sidebarOpen && (
        <div className="mobile-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      <main className="main-content">
        <GenesisNotification />
        <Outlet />
      </main>

      {/* Mobile bottom nav */}
      {isMobile && (
        <nav className="mobile-bottom-nav">
          {mobileNavItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `mobile-nav-item ${isActive ? 'active' : ''}`}
              end={item.path === '/'}
            >
              <span className="mobile-nav-icon">{item.icon}</span>
              <span className="mobile-nav-label">{item.label}</span>
            </NavLink>
          ))}
          <button
            className="mobile-nav-item"
            onClick={() => setSidebarOpen(true)}
          >
            <span className="mobile-nav-icon">☰</span>
            <span className="mobile-nav-label">More</span>
          </button>
        </nav>
      )}
    </div>
  );
}
