/**
 * projectApi.ts — Project CRUD and ingestion endpoints with auth.
 * Uses authenticated apiClient for Bearer token injection.
 */
import api from './apiClient';

export const projectApi = {
  async ingestUpload(projectId: string, files: FileList | File[]) {
    const form = new FormData();
    form.append('project_id', projectId);
    for (const file of Array.from(files)) {
      form.append('files', file, (file as any).webkitRelativePath || file.name);
    }
    const res = await api.post('/api/project/ingest-upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  async getIngestStatus(jobId: string) {
    const res = await api.get(`/api/project/ingest/status/${encodeURIComponent(jobId)}`);
    return res.data;
  },

  async debugPath(folderPath: string) {
    const res = await api.get('/api/project/debug-path', { params: { folder_path: folderPath } });
    return res.data;
  },

  async ingestPath(projectId: string, folderPath: string) {
    const res = await api.post('/api/project/ingest', {
      folder_path: folderPath,
      project_id: projectId,
    });
    return res.data;
  },

  async resetProject(projectId: string) {
    const res = await api.delete('/api/project/reset', { params: { project_id: projectId } });
    return res.data;
  },

  async reindexDelta(projectId: string) {
    const res = await api.post(`/api/projects/${encodeURIComponent(projectId)}/reindex-delta`);
    return res.data;
  },

  async rebuildFull(projectId: string) {
    const res = await api.post(`/api/projects/${encodeURIComponent(projectId)}/rebuild`);
    return res.data;
  },

  async createProject(projectId: string, name: string) {
    const res = await api.post('/api/projects', { project_id: projectId, name });
    return res.data;
  },

  async deleteProject(projectId: string) {
    const res = await api.delete(`/api/projects/${encodeURIComponent(projectId)}`);
    return res.data;
  },
};
