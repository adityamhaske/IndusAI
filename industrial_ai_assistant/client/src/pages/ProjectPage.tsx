// @ts-nocheck
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
    FolderOpen, RefreshCw, Trash2, CheckCircle2, AlertTriangle,
    Loader2, Database, FileText, Cpu, Hash, Upload, FolderSearch, File, Frown, Save, ShieldCheck, XCircle, FileImage, FileBarChart
} from 'lucide-react';
import useAppStore from '../store/useAppStore';
import { getIdToken } from '../services/auth';

/**
 * Authenticated fetch wrapper
 */
async function authFetch(url, options = {}) {
    const token = await getIdToken();
    const headers = { ...(options.headers || {}) };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(url, { ...options, headers });
}

import systemApi from '../services/systemApi';
import { getProjectStatus, resetProject, getProjectFiles } from '../services/knowledgeApi';
import { projectApi } from '../services/projectApi';

// ── Folder Tree Component ───────────────────────────────────────────────────────
const FolderTreeNode = ({ node, level = 0 }) => {
    const [expanded, setExpanded] = useState(level < 1);
    const isFolder = node.type === 'folder';

    return (
        <div className="flex flex-col">
            <div
                className={`flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-industrial-50 select-none ${isFolder ? 'cursor-pointer' : ''}`}
                style={{ paddingLeft: `${level * 16 + 8}px` }}
                onClick={() => isFolder && setExpanded(!expanded)}
            >
                {isFolder ? (
                    <FolderOpen className={`w-4 h-4 flex-shrink-0 transition-transform ${expanded ? 'text-primary-500' : 'text-industrial-400'}`} />
                ) : (
                    <File className="w-4 h-4 text-industrial-300 flex-shrink-0" />
                )}
                <span className={`text-sm truncate ${isFolder ? 'font-medium text-industrial-700' : 'text-industrial-600'}`}>
                    {node.name}
                </span>
                {!isFolder && (
                    <div className="ml-auto flex items-center">
                        <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" title="Indexed" />
                    </div>
                )}
            </div>
            {isFolder && expanded && node.children && (
                <div className="flex flex-col w-full">
                    {node.children.map((child, i) => (
                        <FolderTreeNode key={`${child.path}-${i}`} node={child} level={level + 1} />
                    ))}
                </div>
            )}
        </div>
    );
};

const StatBox = ({ label, value, icon: Icon }: any) => (
    <div className="bg-white p-4 rounded-xl border border-industrial-200 shadow-sm flex items-center gap-3">
        <div className="p-2.5 bg-primary-50 text-primary-600 rounded-lg">
            <Icon className="w-5 h-5" />
        </div>
        <div>
            <div className="text-xs font-semibold text-industrial-500 uppercase tracking-wider">{label}</div>
            <div className="text-lg font-bold text-industrial-900 mt-0.5">{value}</div>
        </div>
    </div>
);

const statusColor = (state: string) => {
    switch (state) {
        case 'READY': return 'bg-green-50 border-green-200 text-green-700';
        case 'FAILED': return 'bg-red-50 border-red-200 text-red-700';
        case 'STALE': return 'bg-yellow-50 border-yellow-200 text-yellow-700';
        case 'INDEXING': return 'bg-blue-50 border-blue-200 text-blue-700';
        default: return 'bg-industrial-50 border-industrial-200 text-industrial-600';
    }
};


// ── Project Page ──────────────────────────────────────────────────────────────
export const ProjectPage = () => {
    const projectId = useAppStore(s => s.activeProjectId) || 'default';
    const deleteProjectAction = useAppStore(s => s.deleteProject);
    const resetProjectData = useAppStore(s => s.resetProjectData);
    const [status, setStatus] = useState(null);
    const [filesTree, setFilesTree] = useState([]);
    const [ingesting, setIngesting] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(null);
    const [error, setError] = useState('');
    const [pathDiag, setPathDiag] = useState(null);
    const [selectedFiles, setSelectedFiles] = useState(null);
    const [folderName, setFolderName] = useState('');
    const [manualPath, setManualPath] = useState('');
    const [useUpload, setUseUpload] = useState(true);

    const pollRef = useRef(null);
    const fileInputRef = useRef(null);

    const setKnowledgeStatus = useAppStore(s => s.setKnowledgeStatus);

    const fetchStatusAndFiles = useCallback(async () => {
        try {
            const [s, f] = await Promise.all([
                getProjectStatus(projectId).catch(() => null),
                getProjectFiles(projectId).catch(() => [])
            ]);
            if (s) {
                setStatus(s);
                // Push to global store so ChatPage & Header reflect updates immediately
                setKnowledgeStatus(s);
            }
            if (f) setFilesTree(f);

            const done = s && ['READY', 'FAILED', 'UNLOADED'].includes(s.index_state);
            if (done && pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
                setIngesting(false);
            }
        } catch { }
    }, [projectId, setKnowledgeStatus]);

    const startPoll = () => {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(fetchStatusAndFiles, 2000);
    };

    useEffect(() => {
        fetchStatusAndFiles();
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [fetchStatusAndFiles]);

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
        setIngesting(true); setUploadProgress({ sent: 0, total: selectedFiles.length, pct: 0, msg: "Uploading..." });

        try {
            const res = await projectApi.ingestUpload(projectId, selectedFiles);
            const jobId = res.job_id;
            
            let elapsed = 0;
            const pollInterval = setInterval(async () => {
                elapsed += 2;
                if (elapsed > 300) { // 5 minutes
                    clearInterval(pollInterval);
                    setIngesting(false);
                    setError("Indexing is taking longer than expected. Check Project Info page in a few minutes or try re-uploading.");
                    setUploadProgress(null);
                    return;
                }
                
                try {
                    const statusRes = await projectApi.getIngestStatus(jobId);
                    if (statusRes.status === 'unknown') {
                        clearInterval(pollInterval);
                        setIngesting(false);
                        setError(statusRes.error || "Job not found. The server may have restarted. Please re-upload your files.");
                        setUploadProgress(null);
                        return;
                    }
                    if (statusRes.status === 'failed') {
                        clearInterval(pollInterval);
                        setIngesting(false);
                        setError(statusRes.error || "Indexing failed.");
                        setUploadProgress(null);
                        return;
                    }
                    
                    setUploadProgress(prev => ({ ...prev, msg: statusRes.progress || "Processing..." }));
                    
                    if (statusRes.status === 'complete') {
                        clearInterval(pollInterval);
                        await fetchStatusAndFiles();
                        setIngesting(false);
                        setUploadProgress(null);
                    }
                } catch (err) {
                    console.error("Poll error", err);
                }
            }, 2000);
            
        } catch (e) {
            setError(e.message || 'Upload failed');
            setIngesting(false);
            setUploadProgress(null);
        }
    };

    const testPath = async () => {
        if (!manualPath.trim()) { setError('Enter a folder path.'); return; }
        setError(''); setPathDiag(null);
        try {
            const diag = await projectApi.debugPath(manualPath.trim());
            setPathDiag(diag);
        } catch { setError('Could not reach backend.'); }
    };

    const startPathIngestion = async () => {
        if (!manualPath.trim()) { setError('Enter a folder path.'); return; }
        setError(''); setPathDiag(null); setIngesting(true); startPoll();
        try {
            await projectApi.ingestPath(projectId, manualPath.trim());
            await fetchStatusAndFiles();
        } catch (e) {
            setError(e.message || 'Ingest failed');
            setIngesting(false);
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        }
    };

    const handleRebuildIndex = async () => {
        if (!window.confirm('Rebuild the entire knowledge index from scratch? This will re-process all files.')) return;
        setError(''); setIngesting(true); startPoll();
        try {
            await projectApi.rebuildFull(projectId);
            await fetchStatusAndFiles();
        } catch (e) {
            setError(e.message || 'Rebuild failed');
            setIngesting(false);
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        }
    };

    const handleReindexDelta = async () => {
        setError(''); setIngesting(true); startPoll();
        try {
            await projectApi.reindexDelta(projectId);
            await fetchStatusAndFiles();
        } catch (e) {
            setError(e.message || 'Reindex failed');
            setIngesting(false);
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        }
    };

    const handleClearFaults = async () => {
        if (!window.confirm('Clear all fault data and analysis results for this project?')) return;
        try {
            await authFetch(`/api/fault/reset?project_id=${projectId}`, { method: 'DELETE' });
            resetProjectData();
        } catch (e) { setError(e.message || 'Failed to clear fault data'); }
    };

    const handleDeleteProject = async () => {
        if (projectId === 'default') { alert('Cannot delete the default project.'); return; }
        if (!window.confirm(`Permanently delete project "${projectId}" and ALL its data? This cannot be undone.`)) return;
        try {
            await deleteProjectAction(projectId);
            window.location.href = '/';
        } catch (e) { setError(e.message || 'Failed to delete project'); }
    };

    return (
        <div className="flex flex-col h-full w-full bg-industrial-50">
            {/* Header */}
            <header className="flex-shrink-0 bg-white border-b border-industrial-200 px-6 py-4 flex items-center justify-between z-10">
                <div className="flex items-center gap-3">
                    <Database className="w-5 h-5 text-primary-600" />
                    <div>
                        <h2 className="text-xl font-bold text-industrial-800">Project Information</h2>
                        <p className="text-xs text-industrial-400 font-medium">Manage operational project data and vector knowledge stores.</p>
                    </div>
                </div>
                {status && (
                    <div className="flex items-center gap-3">
                        {status.index_state === 'INDEXING' && (
                            <span className="text-xs text-industrial-500 font-medium flex items-center gap-1.5 px-3 py-1 bg-industrial-100 rounded-full">
                                <Loader2 className="w-3 h-3 animate-spin" /> Indexing Engine Active
                            </span>
                        )}
                        <span className={`text-xs font-bold px-3 py-1 rounded-full border ${statusColor(status.index_state)} uppercase tracking-wide`}>
                            {status.index_state === 'STALE' ? 'DELTA DETECTED' : status.index_state}
                        </span>
                    </div>
                )}
            </header>

            {/* 2-Column Main Layout */}
            <div className="flex-1 overflow-hidden flex flex-col md:flex-row p-6 gap-6">

                {/* LEFT PANEL: Metadata & Upload Control */}
                <div className="w-full md:w-1/2 lg:w-[55%] flex flex-col gap-6 overflow-y-auto pr-2 pb-6">

                    {/* Telemetry Block */}
                    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                        <StatBox label="Indexed Tags" value={status?.tags_indexed?.toLocaleString()} icon={Cpu} />
                        <StatBox label="L5X Routines" value={status?.routines_indexed?.toLocaleString()} icon={FileText} />
                        <StatBox label="IO Rows" value={status?.io_rows_indexed?.toLocaleString()} icon={Database} />
                        <StatBox label="Semantic Chunks" value={status?.semantic_chunks?.toLocaleString()} icon={FileText} />
                        <StatBox label="Failed Files" value={status?.errors?.length ?? 0} icon={AlertTriangle} />
                        <StatBox label="Index Memory" value={status?.memory_footprint_mb ? `${status.memory_footprint_mb.toFixed(1)} MB` : '—'} icon={Cpu} />
                    </div>

                    {status?.errors?.length > 0 && (
                        <div className="bg-red-50 border border-red-200 rounded-xl p-4 space-y-2">
                            <p className="text-sm font-semibold text-red-700 flex items-center gap-2">
                                <AlertTriangle className="w-4 h-4" /> Ingestion Error Traces
                            </p>
                            <div className="max-h-32 overflow-y-auto text-xs text-red-600 space-y-1 font-mono">
                                {status.errors.map((e, i) => (
                                    <p key={i} className="truncate" title={e}>{e}</p>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Uploader Card */}
                    <div className="bg-white border border-industrial-200 rounded-2xl p-5 shadow-sm space-y-5 flex-shrink-0">
                        <div className="flex items-center justify-between">
                            <h3 className="text-base font-bold text-industrial-800">Add Project Source Data</h3>
                            <div className="flex rounded-lg border border-industrial-200 overflow-hidden text-xs">
                                <button
                                    onClick={() => { setUseUpload('folder'); setError(''); setPathDiag(null); }}
                                    className={`px-3 py-1.5 font-medium transition-colors ${useUpload === 'folder' || useUpload === true ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}
                                >
                                    Folder
                                </button>
                                <button
                                    onClick={() => { setUseUpload('file'); setError(''); setPathDiag(null); }}
                                    className={`px-3 py-1.5 font-medium transition-colors ${useUpload === 'file' ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}
                                >
                                    File
                                </button>
                                <button
                                    onClick={() => { setUseUpload('path'); setError(''); setPathDiag(null); }}
                                    className={`px-3 py-1.5 font-medium transition-colors ${useUpload === 'path' || useUpload === false ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}
                                >
                                    Path
                                </button>
                            </div>
                        </div>

                        {(useUpload === 'folder' || useUpload === true) && (
                            <div className="space-y-4">
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    // @ts-ignore
                                    webkitdirectory="true" directory="true" multiple
                                    className="hidden" onChange={onFolderPicked}
                                    accept=".l5x,.L5X,.xlsx,.xls,.pdf,.txt,.md,.csv"
                                />

                                <div
                                    onClick={() => !ingesting && fileInputRef.current?.click()}
                                    className={`border-2 border-dashed rounded-xl p-6 flex flex-col items-center gap-3 cursor-pointer transition-colors ${folderName
                                        ? 'border-primary-300 bg-primary-50'
                                        : 'border-industrial-200 hover:border-primary-300 hover:bg-primary-50'
                                        } ${ingesting ? 'opacity-50 cursor-not-allowed pointer-events-none' : ''}`}
                                >
                                    <FolderSearch className={`w-8 h-8 ${folderName ? 'text-primary-500' : 'text-industrial-300'}`} />
                                    {folderName ? (
                                        <div className="text-center">
                                            <p className="font-bold text-primary-700 truncate max-w-xs">{folderName}</p>
                                            <p className="text-xs text-primary-500 mt-0.5">{selectedFiles?.length} files scheduled</p>
                                        </div>
                                    ) : (
                                        <div className="text-center">
                                            <p className="font-semibold text-industrial-600">Select source folder...</p>
                                            <p className="text-xs text-industrial-400 mt-1 max-w-xs leading-relaxed">Imports local .L5X logic, IO spreadsheets, and PDF schematics seamlessly into Qdrant.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {useUpload === 'file' && (
                            <div className="space-y-4">
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    multiple
                                    className="hidden" onChange={onFolderPicked}
                                    accept=".l5x,.L5X,.xlsx,.xls,.pdf,.txt,.md,.csv"
                                />

                                <div
                                    onClick={() => !ingesting && fileInputRef.current?.click()}
                                    className={`border-2 border-dashed rounded-xl p-6 flex flex-col items-center gap-3 cursor-pointer transition-colors ${folderName
                                        ? 'border-primary-300 bg-primary-50'
                                        : 'border-industrial-200 hover:border-primary-300 hover:bg-primary-50'
                                        } ${ingesting ? 'opacity-50 cursor-not-allowed pointer-events-none' : ''}`}
                                >
                                    <FileText className={`w-8 h-8 ${folderName ? 'text-primary-500' : 'text-industrial-300'}`} />
                                    {folderName ? (
                                        <div className="text-center">
                                            <p className="font-bold text-primary-700 truncate max-w-xs">{folderName}</p>
                                            <p className="text-xs text-primary-500 mt-0.5">{selectedFiles?.length} files scheduled</p>
                                        </div>
                                    ) : (
                                        <div className="text-center">
                                            <p className="font-semibold text-industrial-600">Select individual files...</p>
                                            <p className="text-xs text-industrial-400 mt-1 max-w-xs leading-relaxed">Upload specific PDF manuals, L5X files, or spreadsheets directly.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {(useUpload === 'path' || useUpload === false) && (
                            <div className="space-y-2">
                                <label className="text-xs font-semibold text-industrial-600 uppercase">Absolute Folder Mount Path</label>
                                <input
                                    type="text" value={manualPath} onChange={e => setManualPath(e.target.value)}
                                    placeholder="/ext-drive/projects/Line6"
                                    className="w-full border border-industrial-200 rounded-xl px-4 py-2 text-sm text-industrial-800 font-mono focus:border-primary-400 focus:ring-1 focus:ring-primary-400 outline-none"
                                />
                            </div>
                        )}

                        {error && (
                            <div className="flex flex-col gap-2 bg-red-50 border border-red-200 rounded-xl p-3">
                                <div className="flex items-start gap-2 text-sm text-red-600">
                                    <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                                    <div><span className="font-medium">Ingestion failed:</span> <br />{error}</div>
                                </div>
                                <div className="flex justify-end">
                                    <button
                                        onClick={() => (useUpload === 'path' || useUpload === false) ? startPathIngestion() : startUploadIngestion()}
                                        className="px-3 py-1.5 text-xs font-semibold text-red-700 bg-red-100 hover:bg-red-200 rounded-lg transition-colors flex items-center gap-1.5"
                                    >
                                        <RefreshCw className="w-3 h-3" /> Retry
                                    </button>
                                </div>
                            </div>
                        )}

                        <div className="flex gap-2 items-center flex-wrap pt-2">
                            {useUpload === 'folder' || useUpload === 'file' || useUpload === true ? (
                                <button
                                    onClick={startUploadIngestion} disabled={ingesting || !selectedFiles}
                                    className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 bg-industrial-900 text-white rounded-xl text-sm font-bold hover:bg-industrial-800 disabled:opacity-50 transition-colors shadow-sm"
                                >
                                    {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                                    {ingesting ? (uploadProgress?.msg || 'Indexing documents...') : 'Upload & Index'}
                                </button>
                            ) : (
                                <>
                                    <button
                                        onClick={testPath} disabled={ingesting || !manualPath.trim()}
                                        className="px-4 py-2.5 border border-industrial-300 text-industrial-600 rounded-xl text-sm font-bold hover:bg-industrial-50 disabled:opacity-40 transition-colors"
                                    >
                                        Validate
                                    </button>
                                    <button
                                        onClick={startPathIngestion} disabled={ingesting || !manualPath.trim()}
                                        className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 bg-industrial-900 text-white rounded-xl text-sm font-bold hover:bg-industrial-800 disabled:opacity-50 transition-colors shadow-sm"
                                    >
                                        {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <FolderOpen className="w-4 h-4" />}
                                        {ingesting ? (uploadProgress?.msg || 'Indexing documents...') : 'Start Indexing'}
                                    </button>
                                </>
                            )}
                            {status?.project_loaded && (
                                <button
                                    onClick={handleReindexDelta} disabled={ingesting}
                                    title="Re-index changed files only (incremental)"
                                    className="flex items-center gap-1.5 px-4 py-2.5 bg-industrial-900 text-white rounded-xl hover:bg-industrial-800 disabled:opacity-40 transition-colors text-xs font-semibold"
                                >
                                    {ingesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                                    Reindex Delta
                                </button>
                            )}
                            {status?.project_loaded && (
                                <button
                                    onClick={handleRebuildIndex} disabled={ingesting}
                                    title="Full rebuild — wipe all embeddings and reindex from scratch"
                                    className="flex items-center gap-1.5 px-3 py-2.5 border border-blue-200 text-blue-600 rounded-xl hover:bg-blue-50 disabled:opacity-40 transition-colors text-xs font-semibold"
                                >
                                    <RefreshCw className="w-3.5 h-3.5" />
                                    Rebuild
                                </button>
                            )}
                            <button
                                onClick={handleClearFaults} disabled={ingesting}
                                title="Clear Fault Data & Analysis"
                                className="flex items-center gap-1.5 px-3 py-2.5 border border-yellow-200 text-yellow-700 rounded-xl hover:bg-yellow-50 disabled:opacity-40 transition-colors text-xs font-semibold"
                            >
                                <Trash2 className="w-3.5 h-3.5" />
                                Clear Faults
                            </button>
                            {projectId !== 'default' && (
                                <button
                                    onClick={handleDeleteProject} disabled={ingesting}
                                    title="Delete Entire Project"
                                    className="flex items-center gap-1.5 px-3 py-2.5 border border-red-300 text-red-600 rounded-xl hover:bg-red-50 disabled:opacity-40 transition-colors text-xs font-semibold"
                                >
                                    <XCircle className="w-3.5 h-3.5" />
                                    Delete Project
                                </button>
                            )}
                        </div>

                    </div>
                </div>

                {/* RIGHT PANEL: Folder Tree Preview */}
                <div className="w-full md:w-1/2 lg:w-[45%] bg-white border border-industrial-200 rounded-2xl flex flex-col shadow-sm overflow-hidden">
                    <div className="px-5 py-4 border-b border-industrial-100 bg-industrial-50 flex items-center justify-between">
                        <h3 className="text-sm font-bold text-industrial-800 flex items-center gap-2">
                            <FolderOpen className="w-4 h-4 text-industrial-500" />
                            Indexed Directory Explorer
                        </h3>
                        <span className="text-xs font-mono text-industrial-400 bg-industrial-200/50 px-2 py-0.5 rounded">
                            /api/project/files
                        </span>
                    </div>
                    <div className="flex-1 overflow-y-auto p-3">
                        {filesTree.length === 0 ? (
                            <div className="h-full flex flex-col items-center justify-center text-center p-6 grayscale opacity-60">
                                <Frown className="w-10 h-10 text-industrial-300 mb-3" />
                                <p className="text-sm font-bold text-industrial-500">No project source data.</p>
                                <p className="text-xs text-industrial-400 max-w-[200px] mt-1">Upload a directory containing PDFs, Excel sheets, and L5X components to see the hybrid searchable tree here.</p>
                            </div>
                        ) : (
                            <div className="space-y-0.5 pl-1">
                                {filesTree.map((node, i) => (
                                    <FolderTreeNode key={`${node.name}-${i}`} node={node} level={0} />
                                ))}
                            </div>
                        )}
                    </div>
                </div>

            </div>
        </div>
    );
};


// ── Settings Page ──────────────────────────────────────────────────────────────
export const SettingsPage = () => {
    const [connectionStatus, setConnectionStatus] = useState(null);
    const [diagnostics, setDiagnostics] = useState(null);
    const [showDiag, setShowDiag] = useState(false);
    const [testing, setTesting] = useState(false);

    const handleTestConnection = async () => {
        setTesting(true);
        setConnectionStatus({ status: 'testing' });
        try {
            const res = await authFetch('/api/ai/test-connection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: 'gemini' }),
            });
            const data = await res.json();
            setConnectionStatus(data);
        } catch {
            setConnectionStatus({ status: 'failed', error: 'Connection test failed' });
        }
        try {
            const diag = await authFetch('/api/ai/providers').then(r => r.json());
            setDiagnostics(diag);
        } catch { /* ignore */ }
        setTesting(false);
    };

    return (
        <div className="h-full overflow-y-auto">
            <div className="p-8 max-w-4xl pb-24">
                <h2 className="text-2xl font-bold text-industrial-800 mb-6">System Settings</h2>

                <div className="space-y-6">
                    {/* Architecture Read-Only Section */}
                    <div className="bg-white p-6 rounded-xl border border-industrial-200 shadow-sm space-y-5">
                        <h3 className="text-lg font-bold text-industrial-800 border-b border-industrial-100 pb-3 flex items-center gap-2">
                            <Cpu className="w-5 h-5 text-primary-600" /> Cloud Native Architecture
                        </h3>

                        <div className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="p-4 rounded-lg border border-industrial-200 bg-industrial-50">
                                    <div className="text-sm font-bold text-industrial-800">LLM Provider</div>
                                    <div className="text-xs text-industrial-500 mt-1">Google Gemini 1.5 Flash (Cloud Run)</div>
                                </div>
                                <div className="p-4 rounded-lg border border-industrial-200 bg-industrial-50">
                                    <div className="text-sm font-bold text-industrial-800">Embeddings</div>
                                    <div className="text-xs text-industrial-500 mt-1">Google Gemini Embeddings API</div>
                                </div>
                            </div>
                            
                            <div className="p-4 rounded-lg border border-industrial-200 bg-industrial-50">
                                <div className="text-sm font-bold text-industrial-800">Vector Database</div>
                                <div className="text-xs text-industrial-500 mt-1">Qdrant Cloud</div>
                            </div>
                        </div>

                        {/* Connection Status */}
                        {connectionStatus && (
                            <div className={`flex items-center gap-2 text-sm font-bold p-3 rounded-lg border ${connectionStatus.status === 'connected'
                                ? 'bg-green-50 border-green-200 text-green-700'
                                : connectionStatus.status === 'testing'
                                    ? 'bg-industrial-50 border-industrial-200 text-industrial-600'
                                    : 'bg-red-50 border-red-200 text-red-700'
                                }`}>
                                {connectionStatus.status === 'connected' && <><CheckCircle2 className="w-4 h-4" /> Connected · {connectionStatus.model} · {connectionStatus.latency_ms}ms</>}
                                {connectionStatus.status === 'testing' && <><Loader2 className="w-4 h-4 animate-spin" /> Testing connection…</>}
                                {connectionStatus.status === 'failed' && <><XCircle className="w-4 h-4" /> Connection Failed: {connectionStatus.error}</>}
                            </div>
                        )}

                        <div className="pt-4 border-t border-industrial-100 flex items-center gap-4">
                            <button
                                onClick={handleTestConnection}
                                disabled={testing}
                                className="bg-primary-600 text-white px-5 py-2.5 rounded-lg text-sm font-bold hover:bg-primary-700 disabled:opacity-50 transition-colors flex items-center gap-2"
                            >
                                {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                                Test Cloud Services Connection
                            </button>
                        </div>
                    </div>

                    {/* ── Diagnostics Panel ──────────────────────────────────────── */}
                    <div className="bg-white rounded-xl border border-industrial-200 shadow-sm overflow-hidden">
                        <button
                            onClick={() => { setShowDiag(!showDiag); if (!diagnostics) authFetch('/api/ai/providers').then(r => r.json()).then(setDiagnostics).catch(() => { }); }}
                            className="w-full text-left px-6 py-4 flex items-center justify-between hover:bg-industrial-50 transition-colors"
                        >
                            <span className="text-sm font-bold text-industrial-700 flex items-center gap-2"><Database className="w-4 h-4 text-industrial-400" /> Developer Diagnostics</span>
                            <span className="text-xs text-industrial-400">{showDiag ? '▲ Collapse' : '▼ Expand'}</span>
                        </button>
                        {showDiag && diagnostics && (
                            <div className="px-6 pb-4 border-t border-industrial-100 space-y-2">
                                <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-industrial-600 pt-3">
                                    <span className="font-bold">Primary</span><span className="font-mono">{diagnostics.primary}</span>
                                    <span className="font-bold">Secondary</span><span className="font-mono">{diagnostics.secondary || 'none'}</span>
                                </div>
                                <div className="pt-2">
                                    <span className="text-xs font-bold text-industrial-600">Registered Providers</span>
                                    <div className="mt-1 space-y-1">
                                        {Object.entries(diagnostics.registered_providers || {}).map(([key, info]) => (
                                            <div key={key} className="flex items-center gap-2 text-xs bg-industrial-50 px-3 py-1.5 rounded">
                                                <span className={`w-2 h-2 rounded-full ${info.has_api_key || info.provider_type === 'local' ? 'bg-green-500' : 'bg-yellow-500'}`} />
                                                <span className="font-mono font-bold">{key}</span>
                                                <span className="text-industrial-400">· {info.provider_type} · {info.model}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

