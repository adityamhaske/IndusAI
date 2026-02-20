/**
 * knowledgeApi.js
 * Single typed JS client for all Knowledge Engine endpoints.
 * All functions return the raw response JSON — callers handle errors.
 */

const BASE = '';  // Vite proxy forwards /api → http://localhost:8001

/**
 * POST /api/knowledge/query
 * Always returns KnowledgeQueryResponse with knowledge_mode field.
 */
export async function queryKnowledge({
  question,
  project_id = 'default',
  top_k = 5,
  selected_files = [],
  selected_folders = [],
  scope_mode = 'GLOBAL'
}) {
  const res = await fetch(`${BASE}/api/knowledge/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question, project_id, top_k,
      selected_files, selected_folders, scope_mode
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
    throw Object.assign(new Error(err.message || 'Knowledge query failed'), { data: err });
  }
  return res.json();
}

/**
 * GET /api/project/status?project_id=X
 * Returns ProjectStatus: index_state, tags_indexed, project_loaded, project_hash, etc.
 */
export async function getProjectStatus(project_id = 'default') {
  const res = await fetch(`${BASE}/api/project/status?project_id=${encodeURIComponent(project_id)}`);
  if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
  return res.json();
}

/**
 * POST /api/project/ingest
 * Body: { folder_path, project_id }
 * Returns IngestionResult
 */
export async function ingestProject({ folder_path, project_id = 'default' }) {
  const res = await fetch(`${BASE}/api/project/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_path, project_id }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
    throw Object.assign(new Error(err.message || 'Ingestion failed'), { data: err });
  }
  return res.json();
}

/**
 * GET /api/project/metrics?project_id=X
 */
export async function getProjectMetrics(project_id = 'default') {
  const res = await fetch(`${BASE}/api/project/metrics?project_id=${encodeURIComponent(project_id)}`);
  if (!res.ok) throw new Error(`Metrics failed: ${res.status}`);
  return res.json();
}

/**
 * GET /api/project/files?project_id=X
 * Returns nested file tree of indexed sources.
 */
export async function getProjectFiles(project_id = 'default') {
  const res = await fetch(`${BASE}/api/project/files?project_id=${encodeURIComponent(project_id)}`);
  if (!res.ok) throw new Error(`Files failed: ${res.status}`);
  return res.json();
}

/**
 * DELETE /api/project/reset?project_id=X
 */
export async function resetProject(project_id = 'default') {
  const res = await fetch(`${BASE}/api/project/reset?project_id=${encodeURIComponent(project_id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Reset failed: ${res.status}`);
  return res.json();
}
