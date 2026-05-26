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


import React from 'react';
import useAppStore from '../store/useAppStore';
import { getIdToken } from '../services/auth';

/**
 * Authenticated fetch wrapper — adds Bearer token to every request.
 * Drop-in replacement for window.fetch in page components.
 */
async function authFetch(url, options = {}) {
    const token = await getIdToken();
    const headers = { ...(options.headers || {}) };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(url, { ...options, headers });
}

export const HistoryPage = () => {
    const [tab, setTab] = useState('all');
    const [sessions, setSessions] = useState([]);
    const [plcSnaps, setPlcSnaps] = useState([]);
    const [sortBy, setSortBy] = useState('recent');
    const [loading, setLoading] = useState(true);
    const [resuming, setResuming] = useState(null);
    const [expanded, setExpanded] = useState(null);
    const [detail, setDetail] = useState(null);
    const activeProjectId = useAppStore(s => s.activeProjectId);

    const fetchSessions = useCallback(async (type, sort) => {
        setLoading(true);
        try {
            const params = new URLSearchParams({ sort_by: sort, limit: 200 });
            if (type && type !== 'all' && type !== 'system') params.set('session_type', type);
            if (activeProjectId) params.set('project_id', activeProjectId);
            const r = await authFetch(`/api/history?${params}`);
            const data = await r.json();
            setSessions(Array.isArray(data) ? data : []);
        } catch { setSessions([]); } finally { setLoading(false); }
    }, [activeProjectId]);

    const fetchPlc = useCallback(async (sort) => {
        try {
            const r = await authFetch(`/api/history/plc?sort_by=${sort}&limit=200`);
            const data = await r.json();
            setPlcSnaps(Array.isArray(data) ? data : []);
        } catch { setPlcSnaps([]); }
    }, []);

    useEffect(() => {
        if (tab === 'plc') { fetchPlc(sortBy); }
        else { fetchSessions(tab === 'chat' ? 'chat' : tab === 'all' ? null : null, sortBy); }
    }, [tab, sortBy, fetchSessions, fetchPlc, activeProjectId]);

    const handleDelete = async (id, e) => {
        e.stopPropagation();
        if (!window.confirm('Delete this session and all its messages?')) return;
        await authFetch(`/api/history/session/${id}`, { method: 'DELETE' });
        setSessions(ss => ss.filter(s => s.id !== id));
    };

    const handleExpand = async (id) => {
        if (expanded === id) { setExpanded(null); setDetail(null); return; }
        setExpanded(id);
        try {
            const r = await authFetch(`/api/history/session/${id}`);
            setDetail(await r.json());
        } catch { setDetail(null); }
    };

    const handleResume = async (session, e) => {
        e.stopPropagation();
        setResuming(session.id);
        try {
            const r = await authFetch(`/api/history/session/${session.id}/resume`, { method: 'POST' });
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


