/**
 * faultApi.ts — Axios wrappers for PLC Fault endpoints.
 * Uses authenticated apiClient with auto Bearer token.
 */
import api from './apiClient';

const BASE = '/api/fault';

export const faultApi = {
  /** Upload a CSV file. Returns UploadResponse. */
  upload: (file: File, projectId = 'default', onProgress?: (e: any) => void) => {
    const form = new FormData();
    form.append('file', file);
    form.append('project_id', projectId);
    return api.post(`${BASE}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    }).then(r => r.data);
  },

  /** Paginated fault rows. */
  list: (page = 1, size = 100, projectId = 'default') =>
    api.get(`${BASE}/list`, { params: { page, size, project_id: projectId } })
      .then(r => r.data),

  /** Summary stats. */
  summary: (projectId = 'default') =>
    api.get(`${BASE}/summary`, { params: { project_id: projectId } })
      .then(r => r.data),

  /** Single row detail + history. */
  detail: (rowId: string | number, projectId = 'default') =>
    api.get(`${BASE}/detail`, { params: { row_id: rowId, project_id: projectId } })
      .then(r => r.data),

  /** Deterministic quick stats for dual-engine view */
  quickStats: (rowId: string | number, projectId = 'default') =>
    api.get(`${BASE}/quick-stats`, { params: { row_id: rowId, project_id: projectId } })
      .then(r => r.data),

  /** LLM analysis for a row. */
  analyze: (rowId: string | number, question: string | null = null, projectId = 'default') =>
    api.post(`${BASE}/analyze`, {
      row_id: rowId,
      project_id: projectId,
      ...(question ? { question } : {}),
    }).then(r => r.data),

  /** Clear dataset. */
  reset: (projectId = 'default') =>
    api.delete(`${BASE}/reset`, { params: { project_id: projectId } })
      .then(r => r.data),

  /** Observability metrics. */
  metrics: (projectId = 'default') =>
    api.get(`${BASE}/metrics`, { params: { project_id: projectId } })
      .then(r => r.data),
};
