import React from 'react';

export const LogsPage = () => (
    <div className="p-8">
        <h2 className="text-2xl font-bold text-industrial-800 mb-4">PLC Fault Logs</h2>
        <div className="bg-white p-6 rounded-lg border border-industrial-200 shadow-sm text-center py-20">
            <p className="text-industrial-500">Use the PLC Logs tab in the sidebar.</p>
        </div>
    </div>
);

export const HistoryPage = () => (
    <div className="p-8">
        <h2 className="text-2xl font-bold text-industrial-800 mb-4">Session History</h2>
        <div className="bg-white p-6 rounded-lg border border-industrial-200 shadow-sm text-center py-20">
            <p className="text-industrial-500">History view coming soon.</p>
        </div>
    </div>
);

export const ProjectPage = () => (
    <div className="p-8">
        <h2 className="text-2xl font-bold text-industrial-800 mb-4">Project Information</h2>
        <div className="bg-white p-6 rounded-lg border border-industrial-200 shadow-sm text-center py-20">
            <p className="text-industrial-500">Use Settings to manage the knowledge base.</p>
        </div>
    </div>
);

// ── Settings Page ──────────────────────────────────────────────────────────────
import { useState, useEffect, useRef, useCallback } from 'react';
import {
    FolderOpen, RefreshCw, Trash2, CheckCircle2, AlertTriangle,
    Loader2, Database, FileText, Cpu, Hash, Upload, FolderSearch
} from 'lucide-react';
import { getProjectStatus, resetProject } from '../api/knowledgeApi';

const STATE_COLORS = {
    READY: 'text-green-600 bg-green-50 border-green-200',
    INDEXING: 'text-blue-600 bg-blue-50 border-blue-200',
    STALE: 'text-yellow-600 bg-yellow-50 border-yellow-200',
    FAILED: 'text-red-600 bg-red-50 border-red-200',
    UNLOADED: 'text-industrial-500 bg-industrial-50 border-industrial-200',
};

function statusColor(state) {
    return STATE_COLORS[state] || STATE_COLORS.UNLOADED;
}

const StatBox = ({ label, value, icon: Icon }) => (
    <div className="flex flex-col gap-1 bg-white border border-industrial-200 rounded-xl p-4">
        <div className="flex items-center gap-1.5 text-xs text-industrial-400 font-medium uppercase tracking-wide">
            {Icon && <Icon className="w-3.5 h-3.5" />}
            {label}
        </div>
        <p className="text-2xl font-bold text-industrial-800 tabular-nums">{value ?? '—'}</p>
    </div>
);

export const SettingsPage = () => {
    const [projectId] = useState('default');
    const [status, setStatus] = useState(null);
    const [ingesting, setIngesting] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(null); // {sent, total, pct}
    const [error, setError] = useState('');
    const [pathDiag, setPathDiag] = useState(null);
    const [selectedFiles, setSelectedFiles] = useState(null); // FileList
    const [folderName, setFolderName] = useState('');
    const [manualPath, setManualPath] = useState('');
    const [useUpload, setUseUpload] = useState(true); // true = folder picker, false = path

    const pollRef = useRef(null);
    const fileInputRef = useRef(null);

    // ── Status polling ──────────────────────────────────────────────────────────
    const fetchStatus = useCallback(async () => {
        try {
            const s = await getProjectStatus(projectId);
            setStatus(s);
            const done = ['READY', 'FAILED', 'UNLOADED'].includes(s.index_state);
            if (done && pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
                setIngesting(false);
            }
        } catch { /* leave as-is */ }
    }, [projectId]);

    const startPoll = () => {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(fetchStatus, 2000);
    };

    useEffect(() => {
        fetchStatus();
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [fetchStatus]);

    // ── Folder picker handler ───────────────────────────────────────────────────
    const onFolderPicked = (e) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        setSelectedFiles(files);
        setError('');
        setPathDiag(null);
        // Extract root folder name from webkitRelativePath
        const first = files[0].webkitRelativePath || files[0].name;
        const root = first.split('/')[0] || 'Selected folder';
        setFolderName(root);
    };

    // ── File upload ingestion ───────────────────────────────────────────────────
    const startUploadIngestion = async () => {
        if (!selectedFiles || selectedFiles.length === 0) {
            setError('Select a folder first.'); return;
        }
        setError(''); setPathDiag(null);
        setIngesting(true); setUploadProgress({ sent: 0, total: selectedFiles.length, pct: 0 });
        startPoll();

        const form = new FormData();
        form.append('project_id', projectId);
        for (const file of selectedFiles) {
            // Preserve relative path as filename so backend can reconstruct tree
            form.append('files', file, file.webkitRelativePath || file.name);
        }

        try {
            const res = await fetch('/api/project/ingest-upload', {
                method: 'POST',
                body: form,
            });
            const data = await res.json();
            if (!res.ok) {
                setError(data.message || `Upload error ${res.status}`);
                setIngesting(false);
                if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            }
            await fetchStatus();
        } catch (e) {
            setError(e.message || 'Upload failed');
            setIngesting(false);
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        } finally {
            setUploadProgress(null);
        }
    };

    // ── Path-based ingestion (fallback) ────────────────────────────────────────
    const testPath = async () => {
        if (!manualPath.trim()) { setError('Enter a folder path.'); return; }
        setError(''); setPathDiag(null);
        try {
            const res = await fetch(`/api/project/debug-path?folder_path=${encodeURIComponent(manualPath.trim())}`);
            setPathDiag(await res.json());
        } catch { setError('Could not reach backend.'); }
    };

    const startPathIngestion = async () => {
        if (!manualPath.trim()) { setError('Enter a folder path.'); return; }
        setError(''); setPathDiag(null); setIngesting(true); startPoll();
        try {
            const res = await fetch('/api/project/ingest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: manualPath.trim(), project_id: projectId }),
            });
            const data = await res.json();
            if (!res.ok) {
                if (data.error && (data.resolved_path || data.provided_path))
                    setPathDiag(data);
                setError(data.message || `Error ${res.status}`);
                setIngesting(false);
                if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
                return;
            }
            await fetchStatus();
        } catch (e) {
            setError(e.message || 'Failed');
            setIngesting(false);
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        }
    };

    const handleReset = async () => {
        if (!window.confirm('Reset project index? This cannot be undone.')) return;
        try {
            await resetProject(projectId);
            setSelectedFiles(null); setFolderName('');
            await fetchStatus();
        } catch (e) { setError(e.message); }
    };

    return (
        <div className="p-6 max-w-3xl space-y-6 overflow-y-auto h-full">
            <div>
                <h2 className="text-2xl font-bold text-industrial-800">Settings</h2>
                <p className="text-sm text-industrial-400 mt-1">Project knowledge base configuration.</p>
            </div>

            {/* ── Project Knowledge Base ─────────────────────────────────────── */}
            <section className="bg-white border border-industrial-200 rounded-2xl p-6 space-y-5 shadow-sm">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Database className="w-5 h-5 text-primary-600" />
                        <h3 className="text-lg font-semibold text-industrial-800">Project Knowledge Base</h3>
                    </div>
                    {/* Mode toggle */}
                    <div className="flex rounded-lg border border-industrial-200 overflow-hidden text-xs">
                        <button
                            onClick={() => { setUseUpload(true); setError(''); setPathDiag(null); }}
                            className={`px-3 py-1.5 font-medium transition-colors ${useUpload ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}
                        >
                            📁 Folder Picker
                        </button>
                        <button
                            onClick={() => { setUseUpload(false); setError(''); setPathDiag(null); }}
                            className={`px-3 py-1.5 font-medium transition-colors ${!useUpload ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}
                        >
                            ⌨ Manual Path
                        </button>
                    </div>
                </div>

                {/* ── FOLDER PICKER MODE ─────────────────────────────────────── */}
                {useUpload ? (
                    <div className="space-y-4">
                        <p className="text-xs text-industrial-400">
                            Select your project folder — works cross-platform, no path copy-paste needed.
                            Supports .L5X, .xlsx, .pdf, .txt, .md, .csv files.
                        </p>

                        {/* Hidden file input */}
                        <input
                            ref={fileInputRef}
                            type="file"
                            // @ts-ignore — webkitdirectory is non-standard
                            webkitdirectory="true"
                            directory="true"
                            multiple
                            className="hidden"
                            onChange={onFolderPicked}
                            accept=".l5x,.L5X,.xlsx,.xls,.pdf,.txt,.md,.csv"
                        />

                        {/* Pick folder button */}
                        <div
                            onClick={() => !ingesting && fileInputRef.current?.click()}
                            className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center gap-3 cursor-pointer transition-colors ${folderName
                                    ? 'border-primary-300 bg-primary-50'
                                    : 'border-industrial-200 hover:border-primary-300 hover:bg-primary-50'
                                } ${ingesting ? 'opacity-50 cursor-not-allowed pointer-events-none' : ''}`}
                        >
                            <FolderSearch className={`w-10 h-10 ${folderName ? 'text-primary-500' : 'text-industrial-300'}`} />
                            {folderName ? (
                                <>
                                    <p className="font-semibold text-primary-700">📁 {folderName}</p>
                                    <p className="text-xs text-primary-500">{selectedFiles?.length} files selected · Click to change</p>
                                </>
                            ) : (
                                <>
                                    <p className="font-medium text-industrial-500">Click to select project folder</p>
                                    <p className="text-xs text-industrial-400">All files will be uploaded to backend for indexing</p>
                                </>
                            )}
                        </div>

                        {/* Upload progress */}
                        {uploadProgress && (
                            <div className="space-y-1.5">
                                <div className="h-2 bg-industrial-100 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-primary-500 transition-all duration-300"
                                        style={{ width: `${uploadProgress.pct}%` }}
                                    />
                                </div>
                                <p className="text-xs text-industrial-400 text-center">
                                    Uploading {uploadProgress.sent} / {uploadProgress.total} files…
                                </p>
                            </div>
                        )}
                    </div>
                ) : (
                    /* ── MANUAL PATH MODE ──────────────────────────────────── */
                    <div className="space-y-3">
                        <label className="text-sm font-medium text-industrial-600">
                            Absolute Folder Path
                        </label>
                        <p className="text-xs text-industrial-400">
                            Backend must have read access to this path. Use "Folder Picker" mode to avoid path issues.
                        </p>
                        <input
                            type="text"
                            value={manualPath}
                            onChange={e => setManualPath(e.target.value)}
                            placeholder="/Users/you/projects/MyPLCProject"
                            className="w-full border border-industrial-200 rounded-xl px-4 py-2.5 text-sm text-industrial-800 placeholder-industrial-300 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-200 font-mono"
                        />
                    </div>
                )}

                {/* Error */}
                {error && (
                    <div className="flex items-start gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl p-3">
                        <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                        {error}
                    </div>
                )}

                {/* Path diagnostic (manual mode) */}
                {pathDiag && (
                    <div className={`rounded-xl border p-4 text-xs font-mono space-y-1.5 ${pathDiag.ok ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'
                        }`}>
                        <p className="font-semibold text-sm font-sans mb-2 flex items-center gap-1.5">
                            {pathDiag.ok
                                ? <><CheckCircle2 className="w-4 h-4" /> Path accessible by backend</>
                                : <><AlertTriangle className="w-4 h-4" /> {pathDiag.error_code || pathDiag.error}</>}
                        </p>
                        <div className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
                            <span className="text-industrial-400">Provided:</span><span className="break-all">{pathDiag.provided_path}</span>
                            <span className="text-industrial-400">Resolved:</span><span className="break-all">{pathDiag.resolved_path}</span>
                            <span className="text-industrial-400">Backend CWD:</span><span className="break-all">{pathDiag.cwd}</span>
                            <span className="text-industrial-400">Container:</span><span>{pathDiag.container_mode ? '🐳 Docker' : '🖥️ Native'}</span>
                        </div>
                        {pathDiag.message && !pathDiag.ok && <p className="mt-1 font-sans text-red-600">{pathDiag.message}</p>}
                    </div>
                )}

                {/* Action buttons */}
                <div className="flex gap-3 flex-wrap items-center">
                    {useUpload ? (
                        <button
                            onClick={startUploadIngestion}
                            disabled={ingesting || !selectedFiles}
                            className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                            {ingesting ? 'Indexing...' : status?.project_loaded ? 'Reindex' : 'Upload & Index'}
                        </button>
                    ) : (
                        <>
                            <button
                                onClick={testPath}
                                disabled={ingesting || !manualPath.trim()}
                                className="flex items-center gap-2 px-4 py-2.5 border border-industrial-300 text-industrial-600 rounded-xl text-sm font-medium hover:bg-industrial-50 disabled:opacity-40 transition-colors"
                            >
                                <FolderOpen className="w-4 h-4" /> Test Path
                            </button>
                            <button
                                onClick={startPathIngestion}
                                disabled={ingesting || !manualPath.trim()}
                                className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            >
                                {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                                {ingesting ? 'Indexing...' : status?.project_loaded ? 'Reindex' : 'Index Project'}
                            </button>
                        </>
                    )}

                    {status?.project_loaded && (
                        <button
                            onClick={handleReset}
                            disabled={ingesting}
                            className="flex items-center gap-2 px-4 py-2.5 border border-red-200 text-red-600 rounded-xl text-sm font-medium hover:bg-red-50 disabled:opacity-40 transition-colors ml-auto"
                        >
                            <Trash2 className="w-4 h-4" /> Reset
                        </button>
                    )}
                </div>

                {/* ── Status panel ─────────────────────────────────────────── */}
                {status && (
                    <div className="space-y-4 pt-2 border-t border-industrial-100">
                        <div className="flex items-center gap-3">
                            <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${statusColor(status.index_state)}`}>
                                {status.index_state}
                            </span>
                            {status.index_state === 'INDEXING' && (
                                <span className="text-xs text-industrial-400 flex items-center gap-1.5">
                                    <Loader2 className="w-3 h-3 animate-spin" /> Indexing in progress…
                                </span>
                            )}
                            {status.index_state === 'STALE' && (
                                <span className="text-xs text-yellow-600">⚠ Folder changed — please Reindex</span>
                            )}
                        </div>

                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                            <StatBox label="Tags" value={status.tags_indexed?.toLocaleString()} icon={Cpu} />
                            <StatBox label="Routines" value={status.routines_indexed?.toLocaleString()} icon={FileText} />
                            <StatBox label="IO Rows" value={status.io_rows_indexed?.toLocaleString()} icon={Database} />
                            <StatBox label="Chunks" value={status.semantic_chunks?.toLocaleString()} icon={FileText} />
                            <StatBox label="Files Failed" value={status.errors?.length ?? 0} icon={AlertTriangle} />
                            <StatBox label="Memory (MB)" value={status.memory_footprint_mb?.toFixed(1)} icon={Cpu} />
                        </div>

                        <div className="text-xs text-industrial-400 font-mono bg-industrial-50 rounded-xl p-3 space-y-1">
                            {status.project_hash && (
                                <div className="flex items-center gap-2">
                                    <Hash className="w-3 h-3" />
                                    Hash: {status.project_hash.slice(0, 16)}…
                                </div>
                            )}
                            {status.last_index_time && <p>Last indexed: {new Date(status.last_index_time).toLocaleString()}</p>}
                            {status.ingestion_duration_ms > 0 && <p>Duration: {(status.ingestion_duration_ms / 1000).toFixed(1)}s</p>}
                            {status.folder && <p className="truncate">Stored: {status.folder}</p>}
                        </div>

                        {status.errors?.length > 0 && (
                            <div className="bg-red-50 border border-red-200 rounded-xl p-3 space-y-1">
                                <p className="text-xs font-semibold text-red-600">Ingestion Errors</p>
                                {status.errors.slice(0, 5).map((e, i) => (
                                    <p key={i} className="text-xs text-red-500 truncate">{e}</p>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </section>
        </div>
    );
};
