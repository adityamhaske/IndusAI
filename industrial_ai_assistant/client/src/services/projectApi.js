// client/src/services/projectApi.js
export const projectApi = {
    async ingestUpload(projectId, files) {
        const form = new FormData();
        form.append('project_id', projectId);
        for (const file of files) {
            form.append('files', file, file.webkitRelativePath || file.name);
        }

        const res = await fetch('/api/project/ingest-upload', {
            method: 'POST',
            body: form,
        });

        const text = await res.text();
        let data = {};
        try { data = text ? JSON.parse(text) : {}; } catch { data.message = text || `Upload error ${res.status}`; }

        if (!res.ok) {
            throw new Error(data.message || `Upload error ${res.status}`);
        }
        return data;
    },

    async getIngestStatus(jobId) {
        const res = await fetch(`/api/project/ingest/status/${encodeURIComponent(jobId)}`);
        if (!res.ok) throw new Error('Could not reach backend to check status.');
        return await res.json();
    },

    async debugPath(folderPath) {
        const res = await fetch(`/api/project/debug-path?folder_path=${encodeURIComponent(folderPath)}`);
        if (!res.ok) throw new Error('Could not reach backend.');
        return await res.json();
    },

    async ingestPath(projectId, folderPath) {
        const res = await fetch('/api/project/ingest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath, project_id: projectId }),
        });

        const text = await res.text();
        let data = {};
        try { data = text ? JSON.parse(text) : {}; } catch { data.message = text || `Ingest error ${res.status}`; }

        if (!res.ok) {
            throw new Error(data.message || `Ingest error ${res.status}`);
        }
        return data;
    },

    async resetProject(projectId) {
        const res = await fetch(`/api/project/reset?project_id=${projectId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to reset project');
        return await res.json();
    },

    async reindexDelta(projectId) {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/reindex-delta`, {
            method: 'POST',
        });
        const text = await res.text();
        let data = {};
        try { data = text ? JSON.parse(text) : {}; } catch { data.message = text || `Reindex error ${res.status}`; }
        if (!res.ok) throw new Error(data.detail || data.message || `Reindex error ${res.status}`);
        return data;
    },

    async rebuildFull(projectId) {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/rebuild`, {
            method: 'POST',
        });
        const text = await res.text();
        let data = {};
        try { data = text ? JSON.parse(text) : {}; } catch { data.message = text || `Rebuild error ${res.status}`; }
        if (!res.ok) throw new Error(data.detail || data.message || `Rebuild error ${res.status}`);
        return data;
    },

    async createProject(projectId, name) {
        const res = await fetch('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: projectId, name }),
        });
        if (!res.ok) throw new Error('Failed to create project');
        return await res.json();
    },

    async deleteProject(projectId) {
        const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to delete project');
        }
        return await res.json();
    },
};
