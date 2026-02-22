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

// ── UI Dependencies ──────────────────────────────────────────────────────────────
import { useState, useEffect, useRef, useCallback } from 'react';
import {
    FolderOpen, RefreshCw, Trash2, CheckCircle2, AlertTriangle,
    Loader2, Database, FileText, Cpu, Hash, Upload, FolderSearch, File, Frown, Save
} from 'lucide-react';
import systemApi from '../services/systemApi';
import { getProjectStatus, resetProject, getProjectFiles } from '../services/knowledgeApi';
import { projectApi } from '../services/projectApi';

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
    <div className="flex flex-col gap-1 bg-white border border-industrial-200 rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-1.5 text-xs text-industrial-400 font-medium uppercase tracking-wide">
            {Icon && <Icon className="w-3.5 h-3.5" />}
            {label}
        </div>
        <p className="text-2xl font-bold text-industrial-800 tabular-nums truncate">{value ?? '—'}</p>
    </div>
);

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

// ── Project Page ──────────────────────────────────────────────────────────────
export const ProjectPage = () => {
    const [projectId] = useState('default');
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

    const fetchStatusAndFiles = useCallback(async () => {
        try {
            const [s, f] = await Promise.all([
                getProjectStatus(projectId).catch(() => null),
                getProjectFiles(projectId).catch(() => [])
            ]);
            if (s) setStatus(s);
            if (f) setFilesTree(f);

            const done = s && ['READY', 'FAILED', 'UNLOADED'].includes(s.index_state);
            if (done && pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
                setIngesting(false);
            }
        } catch { }
    }, [projectId]);

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
        setIngesting(true); setUploadProgress({ sent: 0, total: selectedFiles.length, pct: 0 });
        startPoll();

        const form = new FormData();
        form.append('project_id', projectId);
        for (const file of selectedFiles) {
            form.append('files', file, file.webkitRelativePath || file.name);
        }

        try {
            await projectApi.ingestUpload(projectId, selectedFiles);
            await fetchStatusAndFiles();
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

    const handleReset = async () => {
        if (!window.confirm('Reset project index? This cannot be undone.')) return;
        try {
            await resetProject(projectId);
            setSelectedFiles(null); setFolderName('');
            setFilesTree([]);
            await fetchStatusAndFiles();
        } catch (e) { setError(e.message); }
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
                            {status.index_state}
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
                                    onClick={() => { setUseUpload(true); setError(''); setPathDiag(null); }}
                                    className={`px-3 py-1.5 font-medium transition-colors ${useUpload ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}
                                >
                                    Picker
                                </button>
                                <button
                                    onClick={() => { setUseUpload(false); setError(''); setPathDiag(null); }}
                                    className={`px-3 py-1.5 font-medium transition-colors ${!useUpload ? 'bg-primary-600 text-white' : 'text-industrial-500 hover:bg-industrial-50'}`}
                                >
                                    Path
                                </button>
                            </div>
                        </div>

                        {useUpload ? (
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
                        ) : (
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
                            <div className="flex items-start gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl p-3">
                                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                                <div><span className="font-medium">Ingestion failed:</span> <br />{error}</div>
                            </div>
                        )}

                        <div className="flex gap-2 items-center flex-wrap pt-2">
                            {useUpload ? (
                                <button
                                    onClick={startUploadIngestion} disabled={ingesting || !selectedFiles}
                                    className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 bg-industrial-900 text-white rounded-xl text-sm font-bold hover:bg-industrial-800 disabled:opacity-50 transition-colors shadow-sm"
                                >
                                    {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                                    {ingesting ? 'Indexing documents...' : status?.project_loaded ? 'Reindex Delta' : 'Upload & Index'}
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
                                        {ingesting ? 'Indexing documents...' : 'Start Indexing'}
                                    </button>
                                </>
                            )}
                            {status?.project_loaded && (
                                <button
                                    onClick={handleReset} disabled={ingesting}
                                    title="Wipe Index"
                                    className="p-2.5 border border-red-200 text-red-600 rounded-xl hover:bg-red-50 hover:text-red-700 disabled:opacity-40 transition-colors"
                                >
                                    <Trash2 className="w-4 h-4" />
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
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);

    // Form state
    const [primary, setPrimary] = useState('local_ollama');
    const [secondary, setSecondary] = useState('none');
    const [cfgTimeout, setCfgTimeout] = useState(8000);
    const [speculative, setSpeculative] = useState(true);
    const [openaiKey, setOpenaiKey] = useState('');
    const [geminiKey, setGeminiKey] = useState('');

    useEffect(() => {
        let isMounted = true;
        systemApi.getConfig().then(data => {
            if (!isMounted) return;
            setConfig(data);
            setPrimary(data.primary_provider || 'local_ollama');
            setSecondary(data.secondary_provider || 'none');
            setCfgTimeout(data.timeout_ms || 8000);
            setSpeculative(data.speculative_fallback ?? true);
            setOpenaiKey(data.providers?.openai?.enabled ? '********' : '');
            setGeminiKey(data.providers?.gemini?.enabled ? '********' : '');
            setLoading(false);
        }).catch(e => {
            if (!isMounted) return;
            setError('Failed to load configuration.');
            setLoading(false);
        });
        return () => { isMounted = false; };
    }, []);

    const handleSave = async () => {
        setError(null);
        setSuccess(false);
        setSaving(true);
        try {
            const payload = {
                primary_provider: primary,
                secondary_provider: secondary,
                timeout_ms: parseInt(cfgTimeout, 10),
                max_tokens: 2000,
                speculative_fallback: speculative,
                openai_api_key: openaiKey === '********' ? null : openaiKey,
                gemini_api_key: geminiKey === '********' ? null : geminiKey,
            };
            await systemApi.updateConfig(payload);
            setSuccess(true);
            setTimeout(() => setSuccess(false), 3000);
        } catch (e) {
            setError(e.message || 'Failed to save configuration');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return <div className="p-8 flex items-center gap-3 text-industrial-500"><Loader2 className="w-5 h-5 animate-spin" /> Loading configuration...</div>;
    }

    const needsOpenAI = primary === 'openai' || secondary === 'openai';
    const needsGemini = primary === 'gemini' || secondary === 'gemini';
    const disableSave = (needsOpenAI && !openaiKey) || (needsGemini && !geminiKey);

    return (
        <div className="p-8 max-w-4xl">
            <h2 className="text-2xl font-bold text-industrial-800 mb-6">System Settings</h2>

            <div className="space-y-6">
                {/* AI Provider Section */}
                <div className="bg-white p-6 rounded-xl border border-industrial-200 shadow-sm space-y-5">
                    <h3 className="text-lg font-bold text-industrial-800 border-b border-industrial-100 pb-3 flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-primary-600" /> AI Provider Configuration
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="space-y-2">
                            <label className="text-xs font-semibold text-industrial-600 uppercase">Primary Provider</label>
                            <select
                                value={primary}
                                onChange={e => setPrimary(e.target.value)}
                                className="w-full border border-industrial-200 rounded-lg px-3 py-2 text-sm text-industrial-800 focus:outline-none focus:border-primary-400"
                            >
                                <option value="local_ollama">Local (Ollama)</option>
                                <option value="openai">Cloud (OpenAI / GPT-4o)</option>
                                <option value="gemini">Cloud (Google Gemini)</option>
                            </select>
                        </div>

                        <div className="space-y-2">
                            <label className="text-xs font-semibold text-industrial-600 uppercase">Secondary Fallback</label>
                            <select
                                value={secondary}
                                onChange={e => setSecondary(e.target.value)}
                                disabled={!speculative}
                                className="w-full border border-industrial-200 rounded-lg px-3 py-2 text-sm text-industrial-800 focus:outline-none focus:border-primary-400 disabled:opacity-50 disabled:bg-industrial-50"
                            >
                                <option value="none">None</option>
                                <option value="openai">Cloud (OpenAI / GPT-4o)</option>
                                <option value="gemini">Cloud (Google Gemini)</option>
                            </select>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                        <div className="space-y-2">
                            <label className="text-xs font-semibold text-industrial-600 uppercase">Cloud SLA Timeout (ms)</label>
                            <input
                                type="number"
                                value={cfgTimeout}
                                onChange={e => setCfgTimeout(e.target.value)}
                                className="w-full border border-industrial-200 rounded-lg px-3 py-2 text-sm text-industrial-800 focus:outline-none focus:border-primary-400"
                            />
                            <p className="text-xs text-industrial-400">Local TTFT is dynamically bounded (min 20s).</p>
                        </div>

                        <div className="flex items-center gap-3 pt-6">
                            <input
                                type="checkbox"
                                id="speculative"
                                checked={speculative}
                                onChange={e => setSpeculative(e.target.checked)}
                                className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500 cursor-pointer"
                            />
                            <div className="flex flex-col">
                                <label htmlFor="speculative" className="text-sm font-bold text-industrial-700 cursor-pointer">
                                    Enable Speculative Racing Engine
                                </label>
                                <p className="text-xs text-industrial-400">Fires fallback provider proactively if primary lags.</p>
                            </div>
                        </div>
                    </div>

                    {/* API Keys */}
                    <div className="space-y-4 pt-4 border-t border-industrial-100">
                        <h4 className="text-sm font-bold text-industrial-700">Cloud Credentials</h4>
                        <div className="space-y-3">
                            <div>
                                <label className="text-xs font-medium text-industrial-600 mb-1 flex items-center justify-between">
                                    OpenAI API Key
                                    {(needsOpenAI && !openaiKey) && <span className="text-red-500 font-bold">* REQUIRED *</span>}
                                </label>
                                <input
                                    type="password"
                                    value={openaiKey}
                                    onChange={e => setOpenaiKey(e.target.value)}
                                    placeholder="sk-..."
                                    className="w-full border border-industrial-200 rounded-lg px-3 py-2 text-sm text-industrial-800 focus:outline-none focus:border-primary-400 font-mono"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-industrial-600 mb-1 flex items-center justify-between">
                                    Google Gemini API Key
                                    {(needsGemini && !geminiKey) && <span className="text-red-500 font-bold">* REQUIRED *</span>}
                                </label>
                                <input
                                    type="password"
                                    value={geminiKey}
                                    onChange={e => setGeminiKey(e.target.value)}
                                    placeholder="AIzaSy..."
                                    className="w-full border border-industrial-200 rounded-lg px-3 py-2 text-sm text-industrial-800 focus:outline-none focus:border-primary-400 font-mono"
                                />
                            </div>
                        </div>
                    </div>

                    <div className="pt-4 flex items-center gap-4">
                        <button
                            onClick={handleSave}
                            disabled={saving || disableSave}
                            className="bg-primary-600 text-white px-5 py-2.5 rounded-lg text-sm font-bold hover:bg-primary-700 disabled:opacity-50 transition-colors flex items-center gap-2"
                        >
                            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                            Save Configuration
                        </button>
                        {success && <span className="text-sm font-bold text-green-600 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> Settings deployed live.</span>}
                        {error && <span className="text-sm font-bold text-red-600 flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" /> {error}</span>}
                    </div>
                </div>

                <div className="bg-white p-6 rounded-xl border border-industrial-200 shadow-sm">
                    <h3 className="text-sm font-bold text-industrial-800 mb-2 flex items-center gap-2"><Database className="w-4 h-4 text-rose-500" /> Vector Database</h3>
                    <p className="text-sm text-industrial-500 mb-1">Provider: <strong>Qdrant Native Engine</strong></p>
                    <p className="text-sm text-industrial-500">Endpoint: <strong>localhost:6333</strong></p>
                </div>
            </div>
        </div>
    );
};
