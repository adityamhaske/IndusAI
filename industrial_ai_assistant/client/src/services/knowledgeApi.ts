/**
 * knowledgeApi.ts — Knowledge Engine endpoints with auth.
 * Uses authenticated apiClient for Bearer token injection.
 */
import api from './apiClient';

/** POST /api/knowledge/query */
export async function queryKnowledge({
  question,
  project_id = 'default',
  top_k = 5,
  selected_files = [] as string[],
  selected_folders = [] as string[],
  scope_mode = 'GLOBAL',
}) {
  const res = await api.post('/api/knowledge/query', {
    question, project_id, top_k,
    selected_files, selected_folders, scope_mode,
  });
  return res.data;
}

/** GET /api/project/status?project_id=X */
export async function getProjectStatus(project_id = 'default') {
  const res = await api.get('/api/project/status', { params: { project_id } });
  return res.data;
}

/** POST /api/project/ingest */
export async function ingestProject({ folder_path, project_id = 'default' }: { folder_path: string; project_id?: string }) {
  const res = await api.post('/api/project/ingest', { folder_path, project_id });
  return res.data;
}

/** GET /api/project/metrics?project_id=X */
export async function getProjectMetrics(project_id = 'default') {
  const res = await api.get('/api/project/metrics', { params: { project_id } });
  return res.data;
}

/** GET /api/project/files?project_id=X */
export async function getProjectFiles(project_id = 'default') {
  const res = await api.get('/api/project/files', { params: { project_id } });
  return res.data;
}

/** DELETE /api/project/reset?project_id=X */
export async function resetProject(project_id = 'default') {
  const res = await api.delete('/api/project/reset', { params: { project_id } });
  return res.data;
}
