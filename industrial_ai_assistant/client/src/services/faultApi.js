/**
 * Fault API — Axios wrappers for all 7 PLC Fault endpoints.
 * All requests are routed through the Vite proxy to http://localhost:8001
 */
import axios from 'axios';

const BASE = '/api/fault';

export const faultApi = {
    /** Upload a CSV file. Returns UploadResponse. */
    upload: (file, projectId = 'default', onProgress) => {
        const form = new FormData();
        form.append('file', file);
        form.append('project_id', projectId);
        return axios.post(`${BASE}/upload`, form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: onProgress,
        }).then(r => r.data);
    },

    /** Paginated fault rows. */
    list: (page = 1, size = 100, projectId = 'default') =>
        axios.get(`${BASE}/list`, { params: { page, size, project_id: projectId } })
            .then(r => r.data),

    /** Summary stats (from cache). */
    summary: (projectId = 'default') =>
        axios.get(`${BASE}/summary`, { params: { project_id: projectId } })
            .then(r => r.data),

    /** Single row detail + history. */
    detail: (rowId, projectId = 'default') =>
        axios.get(`${BASE}/detail`, { params: { row_id: rowId, project_id: projectId } })
            .then(r => r.data),

    /** LLM analysis for a row. Optional question enables custom Q&A. */
    analyze: (rowId, question = null, projectId = 'default') =>
        axios.post(`${BASE}/analyze`, {
            row_id: rowId,
            project_id: projectId,
            ...(question ? { question } : {}),
        }).then(r => r.data),

    /** Clear dataset. */
    reset: (projectId = 'default') =>
        axios.delete(`${BASE}/reset`, { params: { project_id: projectId } })
            .then(r => r.data),

    /** Observability metrics. */
    metrics: (projectId = 'default') =>
        axios.get(`${BASE}/metrics`, { params: { project_id: projectId } })
            .then(r => r.data),
};
