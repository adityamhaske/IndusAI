import React, { useEffect, useState, useCallback } from 'react';
import { Cpu, WifiOff, RefreshCw, Database, RotateCcw, ShieldCheck, FolderOpen, ChevronDown } from 'lucide-react';
import systemApi from '../../services/systemApi';
import { getProjectStatus } from '../../services/knowledgeApi';
import useAppStore from '../../store/useAppStore';

function llmLabel(health) {
    if (!health) return 'Unknown';
    const model = health.models_available?.[0]?.split(':')[0] || health.llm_provider || 'LLM';
    return model.charAt(0).toUpperCase() + model.slice(1);
}

const Header = ({ title }) => {
    const [health, setHealth] = useState(null);
    const [projects, setProjects] = useState([]);
    const [activeProject, setActiveProject] = useState(localStorage.getItem('activeProjectId') || 'default');
    const knowledgeStatus = useAppStore(s => s.knowledgeStatus);
    const setKnowledgeStatus = useAppStore(s => s.setKnowledgeStatus);
    const resetAll = useAppStore(s => s.resetAll);

    const fetchProjects = useCallback(async () => {
        try {
            const r = await fetch('/api/projects');
            const data = await r.json();
            if (Array.isArray(data) && data.length > 0) setProjects(data);
        } catch { /* silent */ }
    }, []);

    const fetchAll = useCallback(async () => {
        try {
            const [h, p] = await Promise.allSettled([
                systemApi.health(),
                getProjectStatus('default'),
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
        setActiveProject(pid);
        localStorage.setItem('activeProjectId', pid);
        // Reload knowledge status for the new project
        getProjectStatus(pid).then(s => setKnowledgeStatus(s)).catch(() => { });
    };

    const handleReset = async () => {
        if (!window.confirm('Reset all? This clears chat history, project index, and fault data.')) return;
        await resetAll();
    };

    const llmOk = health?.llm_connected;
    const qdrantOk = health?.vector_store_connected;
    const loaded = knowledgeStatus?.project_loaded;

    // Cloud provider indicators derived from AI health payload
    const registeredProviders = health?.registered_providers || [];
    const openaiActive = registeredProviders.includes('openai');
    const geminiActive = registeredProviders.includes('gemini');

    const getActiveMode = (h) => {
        if (!h || !h.primary_provider) return null;
        if (h.primary_provider.includes('local') && (!h.secondary_provider || h.secondary_provider === 'none')) {
            return 'LOCAL_ONLY';
        }
        if (h.primary_provider.includes('local') && h.secondary_provider) {
            return 'HYBRID';
        }
        return 'CLOUD_PRIMARY';
    };

    const mode = getActiveMode(health);
    const modeColors = {
        LOCAL_ONLY: 'bg-indigo-50 text-indigo-700 border-indigo-200',
        HYBRID: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        CLOUD_PRIMARY: 'bg-sky-50 text-sky-700 border-sky-200'
    };

    return (
        <header className="h-14 bg-white border-b border-industrial-200 flex items-center justify-between px-6 shadow-sm z-10 flex-shrink-0">
            {/* Left */}
            <div className="flex items-center gap-4 min-w-0">
                <h1 className="text-base font-semibold text-industrial-800 truncate">{title}</h1>
                <div className="h-4 w-px bg-industrial-200 hidden md:block flex-shrink-0" />

                {/* Project Selector */}
                <div className="hidden md:flex items-center gap-1 relative">
                    <FolderOpen className="w-3.5 h-3.5 text-industrial-400 flex-shrink-0" />
                    <select
                        value={activeProject}
                        onChange={e => handleProjectSwitch(e.target.value)}
                        className="text-xs text-industrial-700 bg-transparent border-none outline-none cursor-pointer pr-4 font-medium max-w-[140px] truncate appearance-none"
                    >
                        {projects.length === 0 ? (
                            <option value="default">default</option>
                        ) : (
                            projects.map(p => (
                                <option key={p.id} value={p.id}>
                                    {p.name || p.id}
                                    {p.index_status === 'READY' ? ' ✓' : p.index_status === 'VECTOR_MISSING' ? ' ⚠' : ''}
                                </option>
                            ))
                        )}
                    </select>
                    <ChevronDown className="w-3 h-3 text-industrial-400 flex-shrink-0 pointer-events-none -ml-3" />
                </div>

                <div className="h-4 w-px bg-industrial-200 hidden md:block flex-shrink-0" />
                <div className={`hidden md:flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-medium flex-shrink-0 ${loaded ? 'bg-green-50 text-green-700 border-green-200' : 'bg-yellow-50 text-yellow-700 border-yellow-200'
                    }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${loaded ? 'bg-green-500' : 'bg-yellow-500'}`} />
                    {loaded ? 'PROJECT' : 'GENERAL'}
                </div>
                {/* System state */}
                {health !== null && (
                    <div className={`hidden lg:flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-bold flex-shrink-0 ${!llmOk ? 'bg-red-50 text-red-700 border-red-200'
                        : !loaded ? 'bg-yellow-50 text-yellow-700 border-yellow-200'
                            : 'bg-green-50 text-green-700 border-green-200'
                        }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${!llmOk ? 'bg-red-500 animate-pulse' : !loaded ? 'bg-yellow-500' : 'bg-green-500'
                            }`} />
                        {!llmOk ? 'AI DISCONNECTED' : !loaded ? 'NOT INDEXED' : 'READY'}
                    </div>
                )}
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
                {/* Cloud Provider Indicators */}
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
                <button onClick={fetchAll} title="Refresh status" className="p-1.5 text-industrial-300 hover:text-industrial-600 hover:bg-industrial-100 rounded-full transition-colors">
                    <RefreshCw className="w-3.5 h-3.5" />
                </button>
                {/* Global reset — clears everything */}
                <button
                    onClick={handleReset}
                    title="Reset all — chat, project index, fault data"
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 border border-red-200 text-red-500 rounded-lg hover:bg-red-50 transition-colors font-medium"
                >
                    <RotateCcw className="w-3 h-3" />
                    Reset
                </button>
            </div>
        </header>
    );
};

export default Header;
