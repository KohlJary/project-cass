/**
 * Base API configuration - axios instance and interceptors
 */
import axios from 'axios';

// In dev, use localhost. In production (same origin), use relative URLs.
const getApiBase = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (window.location.hostname === 'localhost') return 'http://localhost:8000';
  // Production: same origin, use relative URLs
  return '';
};

export const API_BASE = getApiBase();

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Daemon ID storage key (shared with DaemonContext)
const DAEMON_KEY = 'cass_admin_daemon';

// Add request interceptor to inject daemon_id into all requests
api.interceptors.request.use((config) => {
  const daemonId = localStorage.getItem(DAEMON_KEY);
  if (daemonId) {
    // Add daemon_id as query parameter
    config.params = {
      ...config.params,
      daemon_id: daemonId,
    };
  }
  return config;
});
