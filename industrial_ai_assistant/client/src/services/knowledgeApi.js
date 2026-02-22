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
    const text = await res.text();
    let errData = {};
    try { errData = text ? JSON.parse(text) : {}; } catch { errData.message = text || `HTTP ${res.status}`; }
    throw Object.assign(new Error(errData.message || 'Knowledge query failed'), { data: errData });
  }

  const text = await res.text();
  if (!text) throw new Error("Empty response from server");
  return JSON.parse(text);
}

/**
 * GET /api/project/status?project_id=X
 * Returns ProjectStatus: index_state, tags_indexed, project_loaded, project_hash, etc.
 */
export async function getProjectStatus(project_id = 'default') {
  const res = await fetch(`${BASE}/api/project/status?project_id=${encodeURIComponent(project_id)}`);
  if (!res.ok) {
    const text = await res.text();
    let msg = `Status check failed: ${res.status}`;
    try { const data = JSON.parse(text); msg = data.message || msg; } catch { msg = text || msg; }
    throw new Error(msg);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
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
    const text = await res.text();
    let errData = {};
    try { errData = text ? JSON.parse(text) : {}; } catch { errData.message = text || `HTTP ${res.status}`; }
    throw Object.assign(new Error(errData.message || 'Ingestion failed'), { data: errData });
  }
  const text = await res.text();
  if (!text) throw new Error("Empty response from server");
  return JSON.parse(text);
}

/**
 * GET /api/project/metrics?project_id=X
 */
export async function getProjectMetrics(project_id = 'default') {
  const res = await fetch(`${BASE}/api/project/metrics?project_id=${encodeURIComponent(project_id)}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Metrics failed: ${res.status}`);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

/**
 * GET /api/project/files?project_id=X
 * Returns nested file tree of indexed sources.
 */
export async function getProjectFiles(project_id = 'default') {
  const res = await fetch(`${BASE}/api/project/files?project_id=${encodeURIComponent(project_id)}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Files failed: ${res.status}`);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

/**
 * DELETE /api/project/reset?project_id=X
 */
export async function resetProject(project_id = 'default') {
  const res = await fetch(`${BASE}/api/project/reset?project_id=${encodeURIComponent(project_id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Reset failed: ${res.status}`);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : { status: "cleared" };
}
