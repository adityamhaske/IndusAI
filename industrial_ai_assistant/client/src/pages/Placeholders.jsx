import React from 'react';

export const LogsPage = () => (
    <div className="p-8">
        <h2 className="text-2xl font-bold text-industrial-800 mb-4">PLC Fault Logs</h2>
        <div className="bg-white p-6 rounded-lg border border-industrial-200 shadow-sm text-center py-20">
            <p className="text-industrial-500">Use the PLC Logs tab in the sidebar.</p>
        </div>
    </div>
);

export const HistoryPage = () => {
    const [tab, setTab] = useState('all');
    const [sessions, setSessions] = useState([]);
    const [plcSnaps, setPlcSnaps] = useState([]);
    const [sortBy, setSortBy] = useState('recent');
    const [loading, setLoading] = useState(true);
    const [resuming, setResuming] = useState(null);
    const [expanded, setExpanded] = useState(null);
    const [detail, setDetail] = useState(null);

    const fetchSessions = useCallback(async (type, sort) => {
        setLoading(true);
        try {
            const params = new URLSearchParams({ sort_by: sort, limit: 200 });
            if (type && type !== 'all' && type !== 'system') params.set('session_type', type);
            const r = await fetch(`/api/history?${params}`);
            const data = await r.json();
            setSessions(Array.isArray(data) ? data : []);
        } catch { setSessions([]); } finally { setLoading(false); }
    }, []);

    const fetchPlc = useCallback(async (sort) => {
        try {
            const r = await fetch(`/api/history/plc?sort_by=${sort}&limit=200`);
            const data = await r.json();
            setPlcSnaps(Array.isArray(data) ? data : []);
        } catch { setPlcSnaps([]); }
    }, []);

    useEffect(() => {
        if (tab === 'plc') { fetchPlc(sortBy); }
        else { fetchSessions(tab === 'chat' ? 'chat' : tab === 'all' ? null : null, sortBy); }
    }, [tab, sortBy, fetchSessions, fetchPlc]);

    const handleDelete = async (id, e) => {
        e.stopPropagation();
        if (!window.confirm('Delete this session and all its messages?')) return;
        await fetch(`/api/history/session/${id}`, { method: 'DELETE' });
        setSessions(ss => ss.filter(s => s.id !== id));
    };

    const handleExpand = async (id) => {
        if (expanded === id) { setExpanded(null); setDetail(null); return; }
        setExpanded(id);
        try {
            const r = await fetch(`/api/history/session/${id}`);
            setDetail(await r.json());
        } catch { setDetail(null); }
    };

    const handleResume = async (session, e) => {
        e.stopPropagation();
        setResuming(session.id);
        try {
            const r = await fetch(`/api/history/session/${session.id}/resume`, { method: 'POST' });
            const payload = await r.json();
            // Load messages into app store then navigate to chat
            const { useChatStore } = await import('../store/useAppStore').catch(() => ({ useChatStore: null }));
            const store = window.__appStore;
            if (store) {
                const msgs = (payload.messages || []).map((m, i) => ({
                    id: `resume-${i}`,
                    role: m.role,
                    content: m.content,
                    timestamp: new Date(m.created_at).toLocaleTimeString(),
                }));
                store.getState().setChatHistory?.(msgs);
            }
            window.location.href = '/';
        } catch { alert('Resume failed. Please try again.'); }
        finally { setResuming(null); }
    };

    const TABS = [
        { key: 'all', label: 'All Activity' },
        { key: 'chat', label: 'Chat Sessions' },
        { key: 'plc', label: 'PLC Analyses' },
        { key: 'system', label: 'System Events' },
    ];

    const SORTS = [
        { key: 'recent', label: 'Most Recent' },
        { key: 'oldest', label: 'Oldest' },
        { key: 'provider', label: 'By Provider' },
        { key: 'confidence', label: 'By Confidence' },
        { key: 'tokens', label: 'By Token Usage' },
        { key: 'integrity', label: 'By Integrity' },
    ];

    const PLC_SORTS = [
        { key: 'recent', label: 'Most Recent' },
        { key: 'anomaly', label: 'Anomaly Score' },
        { key: 'fault', label: 'Fault ID' },
        { key: 'integrity', label: 'Integrity Status' },
        { key: 'provider', label: 'Provider' },
    ];

    const providerColor = (p) => {
        if (!p) return 'bg-industrial-100 text-industrial-500';
        if (p.includes('openai')) return 'bg-sky-100 text-sky-700';
        if (p.includes('ollama') || p.includes('local')) return 'bg-indigo-100 text-indigo-700';
        if (p.includes('gemini')) return 'bg-purple-100 text-purple-700';
        return 'bg-industrial-100 text-industrial-500';
    };

    const confidenceBadge = (c) => {
        const score = typeof c === 'number' ? (c * 100).toFixed(0) + '%' : c || '—';
        const color = typeof c === 'number'
            ? c >= 0.75 ? 'bg-green-100 text-green-700' : c >= 0.45 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'
            : 'bg-industrial-100 text-industrial-500';
        return <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${color}`}>{score}</span>;
    };

    const integrityBadge = (status) => {
        const color = status === 'OK' ? 'bg-green-100 text-green-700' : status === 'WARNING' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700';
        return <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${color}`}>{status || 'OK'}</span>;
    };

    const typeIcon = (type) => type === 'plc_analysis' ? '⚙' : '💬';

    const SessionCard = ({ s }) => {
        const isExpanded = expanded === s.id;
        const isResuming = resuming === s.id;
        return (
            <div className="bg-white border border-industrial-200 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow">
                <div
                    onClick={() => handleExpand(s.id)}
                    className="px-5 py-4 cursor-pointer hover:bg-industrial-50 transition-colors"
                >
                    <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                            <span className="text-lg flex-shrink-0">{typeIcon(s.session_type)}</span>
                            <div className="min-w-0">
                                <p className="text-sm font-semibold text-industrial-800 truncate">{s.title}</p>
                                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                    <span className="text-[10px] text-industrial-400">
                                        {s.started_at ? new Date(s.started_at).toLocaleString() : '—'}
                                    </span>
                                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${providerColor(s.provider)}`}>
                                        {s.provider?.replace('_', ' ') || 'unknown'}
                                    </span>
                                    {integrityBadge(s.integrity_status)}
                                    {s.confidence_score != null && confidenceBadge(s.confidence_score)}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                            <span className="text-[10px] text-industrial-400 font-mono">
                                {s.total_tokens > 0 ? `${s.total_tokens.toLocaleString()} tok` : ''}
                                {s.latency_ms > 0 ? ` · ${s.latency_ms.toLocaleString()}ms` : ''}
                            </span>
                            <button
                                onClick={(e) => handleResume(s, e)}
                                disabled={isResuming}
                                className="text-xs font-bold text-primary-600 border border-primary-200 bg-primary-50 px-2.5 py-1 rounded-lg hover:bg-primary-100 transition-colors flex items-center gap-1 disabled:opacity-50"
                            >
                                {isResuming ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                                Continue
                            </button>
                            <button
                                onClick={(e) => handleDelete(s.id, e)}
                                className="text-xs text-red-500 border border-red-100 bg-red-50 px-2 py-1 rounded-lg hover:bg-red-100 transition-colors"
                            >
                                <Trash2 className="w-3 h-3" />
                            </button>
                        </div>
                    </div>
                </div>
                {isExpanded && (
                    <div className="border-t border-industrial-100 px-5 py-3 bg-industrial-50 space-y-2">
                        {detail?.messages ? (
                            <div className="space-y-2 max-h-64 overflow-y-auto">
                                {detail.messages.map((m, i) => (
                                    <div key={i} className={`text-xs px-3 py-2 rounded-lg ${m.role === 'user' ? 'bg-white border border-industrial-200 text-industrial-700' : 'bg-primary-50 border border-primary-100 text-industrial-800'}`}>
                                        <span className="font-bold text-industrial-400 mr-2 uppercase text-[9px]">{m.role}</span>
                                        <span className="line-clamp-3">{m.content}</span>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="flex items-center gap-2 text-xs text-industrial-400">
                                <Loader2 className="w-3 h-3 animate-spin" /> Loading messages…
                            </div>
                        )}
                        <div className="text-[10px] text-industrial-400 font-mono">
                            Index: {detail?.index_version || '—'} · Gateway: {detail?.gateway_version || '—'} · Schema: {detail?.prompt_schema_version || '—'}
                        </div>
                    </div>
                )}
            </div>
        );
    };

    const TimelineRow = ({ s }) => (
        <div className="flex items-start gap-3 py-3 border-b border-industrial-100 last:border-0">
            <span className="text-base mt-0.5 flex-shrink-0">{typeIcon(s.session_type)}</span>
            <div className="flex-1 min-w-0">
                <p className="text-sm text-industrial-800 truncate">
                    <span className="font-semibold">{s.title}</span>
                </p>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                    <span className="text-[10px] text-industrial-400">
                        {s.started_at ? new Date(s.started_at).toLocaleTimeString() : ''}
                    </span>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${providerColor(s.provider)}`}>
                        {s.provider?.replace('local_ollama', 'Ollama').replace('openai', 'OpenAI') || '—'}
                    </span>
                    {s.latency_ms > 0 && <span className="text-[10px] text-industrial-400">{s.latency_ms.toLocaleString()}ms</span>}
                    {integrityBadge(s.integrity_status)}
                </div>
            </div>
            <button
                onClick={(e) => handleResume(s, e)}
                className="text-[10px] text-primary-600 hover:underline flex-shrink-0"
            >
                {resuming === s.id ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Resume →'}
            </button>
        </div>
    );

    return (
        <div className="h-full overflow-y-auto">
            <div className="p-6 max-w-5xl pb-24">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-2xl font-bold text-industrial-800">Intelligence History</h2>
                    <div className="flex items-center gap-2">
                        <select
                            value={sortBy}
                            onChange={e => setSortBy(e.target.value)}
                            className="text-xs border border-industrial-200 rounded-lg px-3 py-1.5 text-industrial-700 bg-white focus:outline-none focus:border-primary-400"
                        >
                            {(tab === 'plc' ? PLC_SORTS : SORTS).map(s => (
                                <option key={s.key} value={s.key}>{s.label}</option>
                            ))}
                        </select>
                        <button
                            onClick={() => { if (tab === 'plc') fetchPlc(sortBy); else fetchSessions(tab === 'chat' ? 'chat' : null, sortBy); }}
                            className="p-1.5 border border-industrial-200 rounded-lg hover:bg-industrial-100 transition-colors text-industrial-500"
                        >
                            <RefreshCw className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>

                {/* Tab Bar */}
                <div className="flex gap-1 mb-6 bg-industrial-100 p-1 rounded-xl w-fit">
                    {TABS.map(t => (
                        <button
                            key={t.key}
                            onClick={() => setTab(t.key)}
                            className={`text-xs font-semibold px-4 py-2 rounded-lg transition-all ${tab === t.key ? 'bg-white text-primary-700 shadow-sm' : 'text-industrial-500 hover:text-industrial-700'
                                }`}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>

                {/* Content */}
                {loading ? (
                    <div className="flex items-center gap-3 text-industrial-500 py-12 justify-center">
                        <Loader2 className="w-5 h-5 animate-spin" /> Loading history…
                    </div>
                ) : (
                    <>
                        {/* All Activity tab */}
                        {tab === 'all' && (
                            sessions.length === 0 ? (
                                <div className="text-center py-20 text-industrial-400">
                                    <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
                                    <p className="font-medium">No activity yet</p>
                                    <p className="text-sm mt-1">Ask a question in Chat Assistant to begin recording sessions.</p>
                                </div>
                            ) : (
                                <div className="bg-white border border-industrial-200 rounded-xl px-5 shadow-sm">
                                    {sessions.map(s => <TimelineRow key={s.id} s={s} />)}
                                </div>
                            )
                        )}

                        {/* Chat Sessions tab */}
                        {tab === 'chat' && (
                            sessions.length === 0 ? (
                                <div className="text-center py-20 text-industrial-400">
                                    <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
                                    <p className="font-medium">No chat sessions yet</p>
                                    <p className="text-sm mt-1">Sessions are recorded automatically after each AI response.</p>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    {sessions.filter(s => s.session_type === 'chat').map(s => (
                                        <SessionCard key={s.id} s={s} />
                                    ))}
                                </div>
                            )
                        )}

                        {/* PLC Analyses tab */}
                        {tab === 'plc' && (
                            plcSnaps.length === 0 ? (
                                <div className="text-center py-20 text-industrial-400">
                                    <Cpu className="w-10 h-10 mx-auto mb-3 opacity-30" />
                                    <p className="font-medium">No PLC analyses recorded yet</p>
                                    <p className="text-sm mt-1">PLC fault analyses are logged here automatically.</p>
                                </div>
                            ) : (
                                <div className="bg-white border border-industrial-200 rounded-xl shadow-sm overflow-hidden">
                                    <table className="w-full text-xs">
                                        <thead className="bg-industrial-50 border-b border-industrial-100">
                                            <tr>
                                                {['Fault ID', 'Time', 'Anomaly', 'Burst Rate', 'Integrity', 'Confidence', 'Provider'].map(h => (
                                                    <th key={h} className="text-left px-4 py-3 font-bold text-industrial-600 uppercase text-[10px]">{h}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {plcSnaps.map(p => (
                                                <tr key={p.id} className="border-b border-industrial-50 hover:bg-industrial-50 transition-colors">
                                                    <td className="px-4 py-3 font-mono font-bold text-industrial-800">{p.fault_id}</td>
                                                    <td className="px-4 py-3 text-industrial-500">{p.created_at ? new Date(p.created_at).toLocaleString() : '—'}</td>
                                                    <td className="px-4 py-3">
                                                        <span className={`font-mono font-bold ${p.anomaly_score > 0.7 ? 'text-red-600' : p.anomaly_score > 0.4 ? 'text-yellow-600' : 'text-green-600'}`}>
                                                            {p.anomaly_score?.toFixed(3) ?? '—'}
                                                        </span>
                                                    </td>
                                                    <td className="px-4 py-3 font-mono text-industrial-600">{p.burst_rate?.toFixed(1) ?? '—'}</td>
                                                    <td className="px-4 py-3">
                                                        {p.integrity_passed
                                                            ? <span className="bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-bold text-[10px]">PASSED</span>
                                                            : <span className="bg-red-100 text-red-700 px-1.5 py-0.5 rounded font-bold text-[10px] animate-pulse">FAILED</span>
                                                        }
                                                    </td>
                                                    <td className="px-4 py-3">{p.ai_confidence != null ? confidenceBadge(p.ai_confidence) : '—'}</td>
                                                    <td className="px-4 py-3">
                                                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${providerColor(p.provider)}`}>
                                                            {p.provider?.replace('local_ollama', 'Ollama') || '—'}
                                                        </span>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )
                        )}

                        {/* System Events tab */}
                        {tab === 'system' && (
                            <div className="bg-white border border-industrial-200 rounded-xl p-6 space-y-4">
                                <div className="flex items-center gap-3 text-sm text-industrial-600">
                                    <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                                    <span>Backend started · {new Date().toLocaleDateString()}</span>
                                </div>
                                <div className="flex items-center gap-3 text-sm text-industrial-600">
                                    <Database className="w-4 h-4 text-blue-500 flex-shrink-0" />
                                    <span>SQLite session store initialized</span>
                                </div>
                                <div className="flex items-center gap-3 text-sm text-industrial-600">
                                    <Cpu className="w-4 h-4 text-indigo-500 flex-shrink-0" />
                                    <span>AI Gateway v3 active · Speculative fallback disabled</span>
                                </div>
                                <p className="text-xs text-industrial-400 pt-2">Detailed system event logging available via <span className="font-mono">GET /api/system/logs</span>.</p>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
};

// ── UI Dependencies ──────────────────────────────────────────────────────────────
import { useState, useEffect, useRef, useCallback } from 'react';
import {
    FolderOpen, RefreshCw, Trash2, CheckCircle2, AlertTriangle,
    Loader2, Database, FileText, Cpu, Hash, Upload, FolderSearch, File, Frown, Save, ShieldCheck, XCircle
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
    const [validateState, setValidateState] = useState({ openai: null, gemini: null }); // null | 'validating' | 'VALID' | 'INVALID'
    const [validateDetail, setValidateDetail] = useState({ openai: null, gemini: null });
    const [connectionStatus, setConnectionStatus] = useState(null); // null | {status, provider, latency_ms, model, error}
    const [diagnostics, setDiagnostics] = useState(null);
    const [showDiag, setShowDiag] = useState(false);

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

    const handleValidateKey = async (provider) => {
        const key = provider === 'openai' ? openaiKey : geminiKey;
        if (!key || key === '********') return;
        setValidateState(prev => ({ ...prev, [provider]: 'validating' }));
        setValidateDetail(prev => ({ ...prev, [provider]: null }));
        try {
            const res = await fetch('/api/ai/validate-provider', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider, api_key: key }),
            });
            const data = await res.json();
            setValidateState(prev => ({ ...prev, [provider]: data.success ? 'VALID' : 'INVALID' }));
            setValidateDetail(prev => ({
                ...prev,
                [provider]: data.success
                    ? `Connected · ${data.model ?? 'unknown'} · ${data.latency_ms}ms`
                    : (data.details || data.error || 'Invalid Key'),
            }));
        } catch (e) {
            setValidateState(prev => ({ ...prev, [provider]: 'INVALID' }));
            setValidateDetail(prev => ({ ...prev, [provider]: 'Connection failed' }));
        }
    };

    // Derive mode from primary/secondary
    const providerMode = primary === 'local_ollama' && (secondary === 'none' || !secondary)
        ? 'local'
        : primary === 'openai' || primary === 'gemini'
            ? 'cloud'
            : 'hybrid';

    const setProviderMode = (mode) => {
        if (mode === 'local') {
            setPrimary('local_ollama');
            setSecondary('none');
        } else if (mode === 'cloud') {
            setPrimary('openai');
            setSecondary('none');
        } else {
            setPrimary('local_ollama');
            setSecondary('openai');
        }
    };

    // After save: test connection + fetch diagnostics
    const handleSaveAndTest = async () => {
        await handleSave();
        setConnectionStatus({ status: 'testing' });
        try {
            const res = await fetch('/api/ai/test-connection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: primary }),
            });
            const data = await res.json();
            setConnectionStatus(data);
        } catch {
            setConnectionStatus({ status: 'failed', error: 'Connection test failed' });
        }
        // Fetch diagnostics
        try {
            const diag = await fetch('/api/ai/providers').then(r => r.json());
            setDiagnostics(diag);
        } catch { /* ignore */ }
    };

    if (loading) {
        return <div className="p-8 flex items-center gap-3 text-industrial-500"><Loader2 className="w-5 h-5 animate-spin" /> Loading configuration...</div>;
    }

    const needsOpenAI = primary === 'openai' || secondary === 'openai';
    const needsGemini = primary === 'gemini' || secondary === 'gemini';
    const openaiInvalid = needsOpenAI && validateState.openai === 'INVALID';
    const geminiInvalid = needsGemini && validateState.gemini === 'INVALID';
    const disableSave = (needsOpenAI && !openaiKey) || (needsGemini && !geminiKey) || openaiInvalid || geminiInvalid;

    return (
        <div className="h-full overflow-y-auto">
            <div className="p-8 max-w-4xl pb-24">
                <h2 className="text-2xl font-bold text-industrial-800 mb-6">System Settings</h2>

                <div className="space-y-6">
                    {/* AI Provider Section */}
                    <div className="bg-white p-6 rounded-xl border border-industrial-200 shadow-sm space-y-5">
                        <h3 className="text-lg font-bold text-industrial-800 border-b border-industrial-100 pb-3 flex items-center gap-2">
                            <Cpu className="w-5 h-5 text-primary-600" /> AI Provider Configuration
                        </h3>

                        <div className="space-y-4">
                            <label className="text-xs font-semibold text-industrial-600 uppercase">AI Provider Mode</label>
                            <div className="space-y-2">
                                {[['local', 'Local LLM (Ollama)', 'Uses your local machine. No API key needed.'],
                                ['cloud', 'Cloud (OpenAI)', 'Requires OpenAI API key. Best quality.'],
                                ['hybrid', 'Hybrid (Local + Cloud Fallback)', 'Tries local first, falls back to cloud.']
                                ].map(([val, label, desc]) => (
                                    <label key={val}
                                        className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${providerMode === val
                                            ? 'border-primary-400 bg-primary-50 ring-1 ring-primary-200'
                                            : 'border-industrial-200 hover:border-industrial-300'
                                            }`}
                                    >
                                        <input
                                            type="radio"
                                            name="providerMode"
                                            value={val}
                                            checked={providerMode === val}
                                            onChange={() => setProviderMode(val)}
                                            className="mt-0.5 w-4 h-4 text-primary-600 focus:ring-primary-500"
                                        />
                                        <div>
                                            <div className="text-sm font-bold text-industrial-800">{label}</div>
                                            <div className="text-xs text-industrial-500">{desc}</div>
                                        </div>
                                    </label>
                                ))}
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
                                        onChange={e => { setOpenaiKey(e.target.value); setValidateState(p => ({ ...p, openai: null })); }}
                                        onBlur={() => handleValidateKey('openai')}
                                        placeholder="sk-..."
                                        className="w-full border border-industrial-200 rounded-lg px-3 py-2 text-sm text-industrial-800 focus:outline-none focus:border-primary-400 font-mono"
                                    />
                                    {validateState.openai === 'validating' && (
                                        <div className="mt-1.5 flex items-center gap-1.5 text-xs text-industrial-500">
                                            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Validating…
                                        </div>
                                    )}
                                    {validateState.openai && validateState.openai !== 'validating' && (
                                        <div className={`mt-1.5 flex items-center gap-1.5 text-xs font-semibold ${validateState.openai === 'VALID' ? 'text-green-600' : 'text-red-600'
                                            }`}>
                                            {validateState.openai === 'VALID' ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                                            {validateDetail.openai}
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-industrial-600 mb-1 flex items-center justify-between">
                                        Google Gemini API Key
                                        {(needsGemini && !geminiKey) && <span className="text-red-500 font-bold">* REQUIRED *</span>}
                                    </label>
                                    <input
                                        type="password"
                                        value={geminiKey}
                                        onChange={e => { setGeminiKey(e.target.value); setValidateState(p => ({ ...p, gemini: null })); }}
                                        onBlur={() => handleValidateKey('gemini')}
                                        placeholder="AIzaSy..."
                                        className="w-full border border-industrial-200 rounded-lg px-3 py-2 text-sm text-industrial-800 focus:outline-none focus:border-primary-400 font-mono"
                                    />
                                    {validateState.gemini === 'validating' && (
                                        <div className="mt-1.5 flex items-center gap-1.5 text-xs text-industrial-500">
                                            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Validating…
                                        </div>
                                    )}
                                    {validateState.gemini && validateState.gemini !== 'validating' && (
                                        <div className={`mt-1.5 flex items-center gap-1.5 text-xs font-semibold ${validateState.gemini === 'VALID' ? 'text-green-600' : 'text-red-600'
                                            }`}>
                                            {validateState.gemini === 'VALID' ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                                            {validateDetail.gemini}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="pt-4 flex items-center gap-4">
                            <button
                                onClick={handleSaveAndTest}
                                disabled={saving || disableSave}
                                className="bg-primary-600 text-white px-5 py-2.5 rounded-lg text-sm font-bold hover:bg-primary-700 disabled:opacity-50 transition-colors flex items-center gap-2"
                            >
                                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                Save & Test Connection
                            </button>
                            {success && <span className="text-sm font-bold text-green-600 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> Settings deployed live.</span>}
                            {error && <span className="text-sm font-bold text-red-600 flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" /> {error}</span>}
                        </div>
                    </div>

                    {/* ── Diagnostics Panel ──────────────────────────────────────── */}
                    <div className="bg-white rounded-xl border border-industrial-200 shadow-sm overflow-hidden">
                        <button
                            onClick={() => { setShowDiag(!showDiag); if (!diagnostics) fetch('/api/ai/providers').then(r => r.json()).then(setDiagnostics).catch(() => { }); }}
                            className="w-full text-left px-6 py-4 flex items-center justify-between hover:bg-industrial-50 transition-colors"
                        >
                            <span className="text-sm font-bold text-industrial-700 flex items-center gap-2"><Cpu className="w-4 h-4 text-industrial-400" /> Developer Diagnostics</span>
                            <span className="text-xs text-industrial-400">{showDiag ? '▲ Collapse' : '▼ Expand'}</span>
                        </button>
                        {showDiag && diagnostics && (
                            <div className="px-6 pb-4 border-t border-industrial-100 space-y-2">
                                <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-industrial-600 pt-3">
                                    <span className="font-bold">Primary</span><span className="font-mono">{diagnostics.primary}</span>
                                    <span className="font-bold">Secondary</span><span className="font-mono">{diagnostics.secondary || '—'}</span>
                                    <span className="font-bold">Circuit State</span>
                                    <span className={`font-bold ${diagnostics.circuit_state === 'CLOSED' ? 'text-green-600' : diagnostics.circuit_state === 'OPEN' ? 'text-red-600' : 'text-yellow-600'}`}>{diagnostics.circuit_state}</span>
                                    <span className="font-bold">Speculative</span><span>{diagnostics.speculative_fallback ? 'Enabled' : 'Disabled'}</span>
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

                    <div className="bg-white p-6 rounded-xl border border-industrial-200 shadow-sm">
                        <h3 className="text-sm font-bold text-industrial-800 mb-2 flex items-center gap-2"><Database className="w-4 h-4 text-rose-500" /> Vector Database</h3>
                        <p className="text-sm text-industrial-500 mb-1">Provider: <strong>Qdrant Native Engine</strong></p>
                        <p className="text-sm text-industrial-500">Endpoint: <strong>localhost:6333</strong></p>
                    </div>
                </div>
            </div>
        </div>
    );
};
