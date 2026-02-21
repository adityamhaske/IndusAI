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

import { useState, useEffect, useRef, useCallback } from 'react';
import {
    FolderOpen, RefreshCw, Trash2, CheckCircle2, AlertTriangle,
    Loader2, Database, FileText, Cpu, Hash, Upload, FolderSearch,
    FileCode, FileSpreadsheet, FileCog, ChevronRight, ChevronDown, File,
    Settings, Server, Brain
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

// ── Recursive File Tree Node ──
const FileTreeNode = ({ node, level = 0 }) => {
    const [expanded, setExpanded] = useState(false);
    const isFolder = node.type === "folder";

    const getIcon = () => {
        if (isFolder) return <FolderOpen className={`w-4 h-4 ${expanded ? 'text-primary-500' : 'text-industrial-400'}`} />;
        const name = node.name.toLowerCase();
        if (name.endsWith('.l5x')) return <FileCode className="w-4 h-4 text-orange-500" />;
        if (name.endsWith('.xlsx') || name.endsWith('.csv')) return <FileSpreadsheet className="w-4 h-4 text-green-600" />;
        if (name.endsWith('.pdf')) return <FileCog className="w-4 h-4 text-red-500" />;
        return <File className="w-4 h-4 text-industrial-400" />;
    };

    return (
        <div className="text-sm font-mono filter-none select-none">
            <div
                className={`flex items-center gap-2 py-1.5 px-2 hover:bg-industrial-50 rounded cursor-pointer ${level === 0 ? 'font-semibold text-industrial-800' : 'text-industrial-600'}`}
                style={{ paddingLeft: `${level * 16 + 8}px` }}
                onClick={() => isFolder && setExpanded(!expanded)}
            >
                <div className="w-4 h-4 flex items-center justify-center flex-shrink-0">
                    {isFolder ? (
                        expanded ? <ChevronDown className="w-3.5 h-3.5 text-industrial-400" /> : <ChevronRight className="w-3.5 h-3.5 text-industrial-400" />
                    ) : null}
                </div>
                {getIcon()}
                <span className="truncate">{node.name}</span>
            </div>

            {isFolder && expanded && node.children && (
                <div className="flex flex-col relative w-full">
                    <div className="absolute left-[22px] top-0 bottom-0 w-px bg-industrial-200" style={{ left: `${level * 16 + 26}px` }} />
                    {node.children.map((child, i) => (
                        <FileTreeNode key={`${child.path}-${i}`} node={child} level={level + 1} />
                    ))}
                </div>
            )}
        </div>
    );
};

export const ProjectPage = () => {
    const [projectId] = useState('default');
    const [status, setStatus] = useState(null);
    const [ingesting, setIngesting] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(null);
    const [error, setError] = useState('');
    const [pathDiag, setPathDiag] = useState(null);
    const [selectedFiles, setSelectedFiles] = useState(null);
    const [folderName, setFolderName] = useState('');
    const [manualPath, setManualPath] = useState('');
    const [useUpload, setUseUpload] = useState(true);
    const [fileTree, setFileTree] = useState(null);

    const pollRef = useRef(null);
    const fileInputRef = useRef(null);

    const fetchTree = useCallback(async () => {
        try {
            const res = await fetch(`/api/project/files?project_id=${projectId}`);
            if (res.ok) setFileTree(await res.json());
        } catch { /* ignore */ }
    }, [projectId]);

    const fetchStatus = useCallback(async () => {
        try {
            const s = await getProjectStatus(projectId);
            setStatus(s);
            const done = ['READY', 'FAILED', 'UNLOADED'].includes(s.index_state);
            if (done && pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
                setIngesting(false);
                if (s.index_state === 'READY') fetchTree();
            }
        } catch { /* ignore */ }
    }, [projectId, fetchTree]);

    const startPoll = () => {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(fetchStatus, 2000);
    };

    useEffect(() => {
        fetchStatus();
        fetchTree();
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [fetchStatus, fetchTree]);

    const onFolderPicked = (e) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        setSelectedFiles(files);
        setError('');
        setPathDiag(null);
        const first = files[0].webkitRelativePath || files[0].name;
        const root = first.split('/')[0] || 'Selected folder';
        setFolderName(root);
    };

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
            form.append('files', file, file.webkitRelativePath || file.name);
        }

        try {
            const res = await fetch('/api/project/ingest-upload', { method: 'POST', body: form });
            const text = await res.text();
            let data = {};
            try { data = text ? JSON.parse(text) : {}; } catch { data.message = text || `Upload error ${res.status}`; }
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
            const text = await res.text();
            let data = {};
            try { data = text ? JSON.parse(text) : {}; } catch { data.message = text || `Error ${res.status}`; }

            if (!res.ok) {
                if (data.error && (data.resolved_path || data.provided_path)) setPathDiag(data);
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
            setSelectedFiles(null); setFolderName(''); setFileTree(null);
            await fetchStatus();
        } catch (e) { setError(e.message); }
    };

    return (
        <div className="p-6 h-full flex flex-col items-center">
            <div className="w-full max-w-6xl space-y-6 flex-1 flex flex-col">
                <div>
                    <h2 className="text-2xl font-bold text-industrial-800">Project Workspace</h2>
                    <p className="text-sm text-industrial-400 mt-1">Manage knowledge base indexing and telemetry configurations.</p>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start flex-1 min-h-0">

                    {/* ── LEFT PANEL: Controls & Status ── */}
                    <div className="space-y-6 overflow-y-auto pr-2 pb-6">
                        <section className="bg-white border border-industrial-200 rounded-2xl p-6 shadow-sm space-y-5">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Database className="w-5 h-5 text-primary-600" />
                                    <h3 className="text-lg font-semibold text-industrial-800">Knowledge Indexing</h3>
                                </div>
                                <div className="flex rounded-lg border border-industrial-200 overflow-hidden text-xs">
                                    <button onClick={() => { setUseUpload(true); setError(''); setPathDiag(null); }} className={`px-3 py-1.5 font-medium transition-colors ${useUpload ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}>📁 Upload</button>
                                    <button onClick={() => { setUseUpload(false); setError(''); setPathDiag(null); }} className={`px-3 py-1.5 font-medium transition-colors ${!useUpload ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}>⌨ Path</button>
                                </div>
                            </div>

                            {useUpload ? (
                                <div className="space-y-4">
                                    <input ref={fileInputRef} type="file" webkitdirectory="true" directory="true" multiple className="hidden" onChange={onFolderPicked} accept=".l5x,.L5X,.xlsx,.xls,.pdf,.txt,.md,.csv" />
                                    <div onClick={() => !ingesting && fileInputRef.current?.click()} className={`border-2 border-dashed rounded-xl p-6 flex flex-col items-center gap-2 cursor-pointer transition-colors ${folderName ? 'border-primary-300 bg-primary-50' : 'border-industrial-200 hover:border-primary-300 hover:bg-primary-50'} ${ingesting ? 'opacity-50 pointer-events-none' : ''}`}>
                                        <FolderSearch className={`w-8 h-8 ${folderName ? 'text-primary-500' : 'text-industrial-300'}`} />
                                        {folderName ? (
                                            <div className="text-center"><p className="font-semibold text-primary-700">📁 {folderName}</p><p className="text-xs text-primary-500">{selectedFiles?.length} files selected</p></div>
                                        ) : (
                                            <div className="text-center"><p className="font-medium text-industrial-500">Pick Folder</p></div>
                                        )}
                                    </div>
                                    {uploadProgress && (
                                        <div className="space-y-1.5"><div className="h-1.5 bg-industrial-100 rounded-full overflow-hidden"><div className="h-full bg-primary-500 transition-all" style={{ width: `${uploadProgress.pct}%` }} /></div><p className="text-xs text-industrial-400 text-center">Uploading {uploadProgress.sent} / {uploadProgress.total}…</p></div>
                                    )}
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    <input type="text" value={manualPath} onChange={e => setManualPath(e.target.value)} placeholder="Absolute path" className="w-full border border-industrial-200 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:border-primary-400" />
                                </div>
                            )}

                            {error && (
                                <div className="flex flex-col gap-1 text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl p-4">
                                    <div className="flex items-center gap-2 font-semibold">
                                        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                                        Indexing Failed
                                    </div>
                                    <div className="pl-6 text-xs font-mono">{error}</div>
                                </div>
                            )}

                            {pathDiag && (
                                <div className={`rounded-xl border p-4 text-xs font-mono space-y-1.5 ${pathDiag.ok ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
                                    <p className="font-semibold text-sm font-sans mb-2 flex items-center gap-1.5">
                                        {pathDiag.ok ? <><CheckCircle2 className="w-4 h-4" /> Valid</> : <><AlertTriangle className="w-4 h-4" /> {pathDiag.error_code || pathDiag.error}</>}
                                    </p>
                                    <div className="grid grid-cols-[max-content_1fr] gap-x-2 gap-y-1"><span>Provided:</span><span className="break-all">{pathDiag.provided_path}</span><span>Resolved:</span><span className="break-all">{pathDiag.resolved_path}</span></div>
                                    {pathDiag.message && !pathDiag.ok && <p className="mt-1 font-sans text-red-600">{pathDiag.message}</p>}
                                </div>
                            )}

                            <div className="flex gap-3 flex-wrap">
                                {useUpload ? (
                                    <button onClick={startUploadIngestion} disabled={ingesting || !selectedFiles} className="flex flex-1 items-center justify-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-40 transition-colors">
                                        {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                                        {ingesting ? 'Indexing documents...' : status?.project_loaded ? 'Reindex' : 'Upload & Index'}
                                    </button>
                                ) : (
                                    <>
                                        <button onClick={testPath} disabled={ingesting || !manualPath.trim()} className="flex items-center gap-2 px-4 py-2.5 border border-industrial-300 text-industrial-600 rounded-xl text-sm font-medium hover:bg-industrial-50 disabled:opacity-40 transition-colors">
                                            <FolderOpen className="w-4 h-4" /> Test Path
                                        </button>
                                        <button onClick={startPathIngestion} disabled={ingesting || !manualPath.trim()} className="flex flex-1 items-center justify-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-40 transition-colors">
                                            {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                                            {ingesting ? 'Indexing documents...' : status?.project_loaded ? 'Reindex' : 'Index'}
                                        </button>
                                    </>
                                )}
                                {status?.project_loaded && (
                                    <button onClick={handleReset} disabled={ingesting} className="flex px-4 py-2.5 border border-red-200 text-red-600 rounded-xl text-sm font-medium hover:bg-red-50 disabled:opacity-40 transition-colors">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                )}
                            </div>
                        </section>

                        {status && status.index_state !== 'UNLOADED' && (
                            <section className="bg-white border border-industrial-200 rounded-2xl p-6 shadow-sm space-y-4">
                                <div className="flex items-center gap-3">
                                    <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${statusColor(status.index_state)}`}>{status.index_state}</span>
                                    {status.index_state === 'INDEXING' && <span className="text-xs text-industrial-400 flex items-center gap-1.5"><Loader2 className="w-3 h-3 animate-spin" /> Processing…</span>}
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                    <StatBox label="Tags" value={status.tags_indexed?.toLocaleString()} icon={Cpu} />
                                    <StatBox label="IO Rows" value={status.io_rows_indexed?.toLocaleString()} icon={Database} />
                                    <StatBox label="Chunks" value={status.semantic_chunks?.toLocaleString()} icon={FileText} />
                                    <StatBox label="Issues" value={status.errors?.length ?? 0} icon={AlertTriangle} />
                                </div>
                            </section>
                        )}
                    </div>

                    {/* ── RIGHT PANEL: File Tree Preview ── */}
                    <div className="bg-white border border-industrial-200 rounded-2xl shadow-sm h-full flex flex-col overflow-hidden max-h-[calc(100vh-140px)]">
                        <div className="px-5 py-4 border-b border-industrial-100 bg-industrial-50/50 flex flex-col gap-1 shrink-0">
                            <h3 className="text-sm font-semibold text-industrial-800 flex items-center gap-2">
                                <FolderSearch className="w-4 h-4 text-industrial-500" />
                                Index Directory Explorer
                            </h3>
                            <p className="text-xs text-industrial-400">Successfully indexed files mapping to the Vector DB.</p>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                            {fileTree ? (
                                <FileTreeNode node={{ name: fileTree.root, type: "folder", children: fileTree.children, path: "/" }} />
                            ) : (
                                <div className="h-full flex flex-col items-center justify-center text-industrial-300 gap-3">
                                    <FileCog className="w-12 h-12 opacity-50" />
                                    <p className="text-sm font-medium">No files indexed in workspace</p>
                                </div>
                            )}
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
};

// ── Settings Page ──────────────────────────────────────────────────────────────
export const SettingsPage = () => {
    return (
        <div className="p-6 max-w-3xl space-y-6 overflow-y-auto h-full mx-auto">
            <div>
                <h2 className="text-2xl font-bold text-industrial-800">System Configuration</h2>
                <p className="text-sm text-industrial-400 mt-1">Global platform settings and connection parameters.</p>
            </div>

            <section className="bg-white border border-industrial-200 rounded-2xl p-6 space-y-6 shadow-sm">

                {/* LM Endpoint */}
                <div className="space-y-3">
                    <div className="flex items-center gap-2 text-industrial-800 font-semibold mb-1">
                        <Brain className="w-4 h-4 text-primary-600" />
                        Language Model (Ollama)
                    </div>
                    <label className="text-xs font-medium text-industrial-500 uppercase tracking-widest">Base API URL</label>
                    <input type="text" disabled value="http://localhost:11434" className="w-full border border-industrial-200 rounded-xl px-4 py-2.5 text-sm bg-industrial-50 text-industrial-500 font-mono cursor-not-allowed" />
                    <p className="text-xs text-industrial-400">Native mapping detected automatically by backend integration.</p>
                </div>

                <div className="h-px bg-industrial-100 my-2" />

                {/* Vector DB Endpoint */}
                <div className="space-y-3">
                    <div className="flex items-center gap-2 text-industrial-800 font-semibold mb-1">
                        <Server className="w-4 h-4 text-primary-600" />
                        Vector Store (Qdrant)
                    </div>
                    <label className="text-xs font-medium text-industrial-500 uppercase tracking-widest">Base API URL</label>
                    <input type="text" disabled value="http://localhost:6333" className="w-full border border-industrial-200 rounded-xl px-4 py-2.5 text-sm bg-industrial-50 text-industrial-500 font-mono cursor-not-allowed" />
                </div>

                <div className="h-px bg-industrial-100 my-2" />

                <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-xl text-yellow-700 text-sm">
                    <strong>Note:</strong> Project-specific knowledge base indexing has been moved to the <b>Project Info</b> tab.
                </div>

            </section>
        </div>
    );
};
