/**
 * userApi.ts — User settings / BYOK endpoints.
 */
import api from './apiClient';

const BASE = '/api/user';

export const userApi = {
  getSettings: () => api.get(`${BASE}/settings`).then(r => r.data),

  saveSettings: (payload: {
    llm_provider?: string;
    llm_model?: string;
    llm_api_key?: string;
    embedding_provider?: string;
    embedding_api_key?: string;
    ollama_url?: string;
  }) => api.post(`${BASE}/settings`, payload).then(r => r.data),

  testConnection: () => api.post(`${BASE}/test-connection`).then(r => r.data),
};
