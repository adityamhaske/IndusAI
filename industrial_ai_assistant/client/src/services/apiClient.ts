/**
 * apiClient.ts — Centralized Axios instance with auth interceptor.
 *
 * Every request to /api automatically gets an Authorization: Bearer header
 * with the current Firebase ID token.
 *
 * Usage:
 *   import api from './apiClient';
 *   const data = await api.get('/api/system/health');
 */
import axios from 'axios';
import { getIdToken } from './auth';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 60_000,
});

// Attach Firebase ID token to every request
api.interceptors.request.use(async (config) => {
  try {
    const token = await getIdToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // If token fetch fails, send request without auth — backend will 401
  }
  return config;
});

// Auto-redirect on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid — could trigger re-auth here
      console.warn('[apiClient] 401 — user may need to re-authenticate');
    }
    return Promise.reject(error);
  }
);

export default api;
