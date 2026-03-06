import React, { useEffect, useState, useCallback } from 'react';
import { Cpu, WifiOff, RefreshCw, Database, ShieldCheck, FolderOpen, ChevronDown, Plus, X, Loader2 } from 'lucide-react';
import systemApi from '../../services/systemApi';
import { getProjectStatus } from '../../services/knowledgeApi';
import { projectApi } from '../../services/projectApi';
import useAppStore from '../../store/useAppStore';

const llmLabel = (health) => {
    if (!health) return 'Checking...';
    if (!health.llm_connected) return 'Offline';
    return health.llm_provider === 'ollama' ? 'Ollama' : (health.llm_provider || 'LLM');
};

/* Tooltip wrapper — shows a tooltip on hover */
const Tip = ({ text, children }) => (
    <div className="relative group">
        {children}
        <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 bg-industrial-900 text-white text-[11px] rounded-lg shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 leading-relaxed max-w-[220px] whitespace-normal text-center">
            {text}
        </div>
    </div>
);

const Header = ({ title }) => {
    const [health, setHealth] = useState(null);
    const [projects, setProjects] = useState([]);
    const [showNewProject, setShowNewProject] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [creating, setCreating] = useState(false);
    const [reconnecting, setReconnecting] = useState(false);

    const activeProject = useAppStore(s => s.activeProjectId);
    const switchProject = useAppStore(s => s.switchProject);
    const knowledgeStatus = useAppStore(s => s.knowledgeStatus);
    const setKnowledgeStatus = useAppStore(s => s.setKnowledgeStatus);

    const fetchProjects = useCallback(async () => {
        try {
            const r = await fetch('/api/projects');
            const data = await r.json();
            if (Array.isArray(data) && data.length > 0) setProjects(data);
        } catch { /* silent */ }
    }, []);

    const fetchAll = useCallback(async () => {
        try {
            const pid = useAppStore.getState().activeProjectId || 'default';
            const [h, p] = await Promise.allSettled([
                systemApi.health(),
                getProjectStatus(pid),
            ]);
            if (h.status === 'fulfilled') setHealth(h.value);
            if (p.status === 'fulfilled') setKnowledgeStatus(p.value);
        } catch { /* silent */ }
    }, [setKnowledgeStatus]);

    useEffect(() => {
        fetchAll();
        fetchProjects();
        const t = setInterval(fetchAll, 30_000);
        return () => clearInterval(t);
    }, [fetchAll, fetchProjects]);

    const handleProjectSwitch = (pid) => {
        if (pid === '__new__') {
            setShowNewProject(true);
            return;
        }
        switchProject(pid);
        getProjectStatus(pid).then(s => setKnowledgeStatus(s)).catch(() => { });
        fetchProjects();
    };

    const handleCreateProject = async () => {
        if (!newProjectName.trim()) return;
        setCreating(true);
        try {
            const slug = newProjectName.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
            await projectApi.createProject(slug, newProjectName.trim());
            await fetchProjects();
            switchProject(slug);
            getProjectStatus(slug).then(s => setKnowledgeStatus(s)).catch(() => { });
            setShowNewProject(false);
            setNewProjectName('');
        } catch (err) {
            alert('Failed to create project: ' + err.message);
        } finally {
            setCreating(false);
        }
    };

    const handleReconnect = async () => {
        setReconnecting(true);
        try {
            const result = await systemApi.reconnect();
            if (result.health) setHealth(result.health);
            // Also refresh knowledge status
            const pid = useAppStore.getState().activeProjectId || 'default';
            getProjectStatus(pid).then(s => setKnowledgeStatus(s)).catch(() => { });
        } catch {
            // Fallback: just re-fetch health
            await fetchAll();
        } finally {
            setReconnecting(false);
        }
    };

    const llmOk = health?.llm_connected;
    const qdrantOk = health?.vector_store_connected;
    const loaded = knowledgeStatus?.project_loaded;
    const registeredProviders = health?.registered_providers || [];
    const openaiActive = registeredProviders.includes('openai');
    const geminiActive = registeredProviders.includes('gemini');

    const getActiveMode = (h) => {
        if (!h || !h.primary_provider) return null;
        if (h.primary_provider.includes('local') && (!h.secondary_provider || h.secondary_provider === 'none')) return 'LOCAL_ONLY';
        if (h.primary_provider.includes('local') && h.secondary_provider) return 'HYBRID';
        return 'CLOUD_PRIMARY';
    };
    const mode = getActiveMode(health);
    const modeColors = {
        LOCAL_ONLY: 'bg-indigo-50 text-indigo-700 border-indigo-200',
        HYBRID: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        CLOUD_PRIMARY: 'bg-sky-50 text-sky-700 border-sky-200'
    };

    /* Uniform badge style */
    const greenBadge = "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-semibold bg-green-50 text-green-700 border-green-200";
    const warnBadge = "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-semibold bg-yellow-50 text-yellow-700 border-yellow-200";
    const dangerBadge = "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-semibold bg-red-50 text-red-700 border-red-200";

    return (
        <>
            <header className="h-14 bg-white border-b border-industrial-200 flex items-center justify-between px-6 shadow-sm z-10 flex-shrink-0">
                {/* Left — Fixed title area */}
                <div className="flex items-center gap-4 min-w-0">
                    <h1 className="text-base font-semibold text-industrial-800 w-[140px] flex-shrink-0 truncate">{title}</h1>
                    <div className="h-4 w-px bg-industrial-200 hidden md:block flex-shrink-0" />

                    {/* Project Selector */}
                    <div className="hidden md:flex items-center gap-1 relative flex-shrink-0">
                        <FolderOpen className="w-3.5 h-3.5 text-industrial-400 flex-shrink-0" />
                        <select
                            value={activeProject}
                            onChange={e => handleProjectSwitch(e.target.value)}
                            className="text-xs text-industrial-700 bg-transparent border-none outline-none cursor-pointer pr-4 font-medium max-w-[160px] truncate appearance-none"
                        >
                            {projects.length === 0 ? (
                                <option value="default">Default</option>
                            ) : (
                                projects.map(p => (
                                    <option key={p.id} value={p.id}>
                                        {p.name || p.id}
                                        {p.index_status === 'READY' ? ' ✓' : p.index_status === 'VECTOR_MISSING' ? ' ⚠' : ''}
                                    </option>
                                ))
                            )}
                            <option value="__new__">＋ New Project...</option>
                        </select>
                        <ChevronDown className="w-3 h-3 text-industrial-400 flex-shrink-0 pointer-events-none -ml-3" />
                    </div>

                    <div className="h-4 w-px bg-industrial-200 hidden md:block flex-shrink-0" />

                    {/* Uniform green badges with tooltips */}
                    <Tip text="Your indexed project files are loaded and active. The AI will use this knowledge to answer questions.">
                        <div className={`hidden md:flex ${loaded ? greenBadge : warnBadge}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${loaded ? 'bg-green-500' : 'bg-yellow-500'}`} />
                            Project
                        </div>
                    </Tip>

                    <Tip text={llmOk ? "All systems operational. LLM and vector store are connected and responding." : "AI engine is disconnected. Click the refresh button to reconnect."}>
                        <div className={`hidden md:flex ${llmOk && loaded ? greenBadge : !llmOk ? dangerBadge : warnBadge}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${llmOk && loaded ? 'bg-green-500' : !llmOk ? 'bg-red-500 animate-pulse' : 'bg-yellow-500'}`} />
                            {!llmOk ? 'Offline' : loaded ? 'Ready' : 'Not Indexed'}
                        </div>
                    </Tip>
                </div>

                {/* Right */}
                <div className="flex items-center gap-3 flex-shrink-0">
                    {mode && (
                        <div className={`hidden lg:flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-bold flex-shrink-0 ${modeColors[mode]}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${mode === 'LOCAL_ONLY' ? 'bg-indigo-500' : mode === 'HYBRID' ? 'bg-emerald-500' : 'bg-sky-500'}`} />
                            {mode.replace('_', ' ')}
                        </div>
                    )}

                    <div className={`hidden md:flex items-center gap-1.5 text-xs ${llmOk ? 'text-industrial-600' : 'text-red-500'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${llmOk ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
                        <Cpu className="w-3 h-3" />
                        {llmLabel(health)}
                    </div>
                    {openaiActive && (
                        <div className="hidden lg:flex items-center gap-1.5 text-xs text-industrial-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                            <ShieldCheck className="w-3 h-3 text-green-600" />
                            <span>OpenAI</span>
                        </div>
                    )}
                    {geminiActive && (
                        <div className="hidden lg:flex items-center gap-1.5 text-xs text-industrial-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                            <ShieldCheck className="w-3 h-3 text-green-600" />
                            <span>Gemini</span>
                        </div>
                    )}
                    <div className={`hidden md:flex items-center gap-1.5 text-xs ${qdrantOk ? 'text-industrial-600' : 'text-red-500'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${qdrantOk ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
                        <Database className="w-3 h-3" />
                        {qdrantOk ? 'Qdrant' : 'DB Down'}
                    </div>
                    {!llmOk && health !== null && (
                        <div className="flex items-center gap-1.5 text-xs text-red-600 bg-red-50 border border-red-200 px-2.5 py-1 rounded-full">
                            <WifiOff className="w-3 h-3" /> LLM Offline
                        </div>
                    )}

                    {/* Reconnect / Refresh button */}
                    <Tip text="Reconnect LLM & RAG services. Use when AI goes offline or after changing settings.">
                        <button
                            onClick={handleReconnect}
                            disabled={reconnecting}
                            title="Reconnect LLM & RAG"
                            className="p-1.5 text-industrial-300 hover:text-industrial-600 hover:bg-industrial-100 rounded-full transition-colors disabled:opacity-50"
                        >
                            {reconnecting
                                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                : <RefreshCw className="w-3.5 h-3.5" />
                            }
                        </button>
                    </Tip>
                </div>
            </header>

            {/* New Project Modal */}
            {showNewProject && (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setShowNewProject(false)}>
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between px-6 py-4 border-b border-industrial-100">
                            <h2 className="text-lg font-semibold text-industrial-900">Create New Project</h2>
                            <button onClick={() => setShowNewProject(false)} className="p-1 hover:bg-industrial-100 rounded-full transition-colors">
                                <X className="w-4 h-4 text-industrial-400" />
                            </button>
                        </div>
                        <div className="px-6 py-5 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-industrial-700 mb-1.5">Project Name</label>
                                <input
                                    type="text"
                                    value={newProjectName}
                                    onChange={e => setNewProjectName(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && handleCreateProject()}
                                    placeholder="e.g. Water Treatment Plant"
                                    autoFocus
                                    className="w-full px-3.5 py-2.5 border border-industrial-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-industrial-500 focus:border-transparent"
                                />
                                <p className="text-xs text-industrial-400 mt-1.5">Each project has its own documents, PLC logs, and chat history.</p>
                            </div>
                        </div>
                        <div className="flex justify-end gap-3 px-6 py-4 bg-industrial-50 border-t border-industrial-100">
                            <button
                                onClick={() => setShowNewProject(false)}
                                className="px-4 py-2 text-sm text-industrial-600 hover:bg-industrial-100 rounded-lg transition-colors font-medium"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleCreateProject}
                                disabled={!newProjectName.trim() || creating}
                                className="flex items-center gap-2 px-5 py-2 bg-industrial-900 hover:bg-black disabled:bg-industrial-300 text-white rounded-lg text-sm font-semibold transition-colors"
                            >
                                <Plus className="w-4 h-4" />
                                {creating ? 'Creating...' : 'Create Project'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default Header;
