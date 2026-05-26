/**
 * systemApi.ts — System endpoints with auth.
 */
import api from './apiClient';

const BASE = '/api/system';

const systemApi = {
  health: () => api.get(`${BASE}/health`).then(r => r.data),
  getConfig: () => api.get(`${BASE}/config`).then(r => r.data),
  updateConfig: (payload: any) => api.post(`${BASE}/config`, payload).then(r => r.data),
  reconnect: () => api.post(`${BASE}/reconnect`).then(r => r.data),
};

export default systemApi;
