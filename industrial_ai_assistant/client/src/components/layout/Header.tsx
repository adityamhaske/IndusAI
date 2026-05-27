import React, { useEffect, useState, useCallback } from 'react';
import { Cpu, WifiOff, RefreshCw, Database, ShieldCheck, FolderOpen, ChevronDown, Plus, X, Loader2, LogOut } from 'lucide-react';
import systemApi from '../../services/systemApi';
import { getProjectStatus } from '../../services/knowledgeApi';
import { projectApi } from '../../services/projectApi';
import useAppStore from '../../store/useAppStore';
import { firebaseAuth as auth } from '../../config/firebase';

const Tip = ({ text, children }: { text: string, children: React.ReactNode }) => (
    <div className="relative group">
        {children}
        <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 bg-industrial-900 text-white text-[11px] rounded-lg shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 leading-relaxed max-w-[220px] whitespace-normal text-center">
            {text}
        </div>
    </div>
);

const Header = ({ title }: { title: string }) => {
    const [health, setHealth] = useState<any>(null);
    const [projects, setProjects] = useState<any[]>([]);
    const [showNewProject, setShowNewProject] = useState(false);
    const [newProjectName, setNewProjectName] = useState('');
    const [creating, setCreating] = useState(false);
    const [reconnecting, setReconnecting] = useState(false);
    const [showUserMenu, setShowUserMenu] = useState(false);

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
                fetch('/api/health').then(r => r.json()),
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

    const handleProjectSwitch = (pid: string) => {
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
        } catch (err: any) {
            alert('Failed to create project: ' + err.message);
        } finally {
            setCreating(false);
        }
    };

    const handleReconnect = async () => {
        setReconnecting(true);
        try {
            await fetchAll();
        } finally {
            setReconnecting(false);
        }
    };

    const handleSignOut = () => {
        auth.signOut().then(() => {
            window.location.reload();
        });
    };

    const { user: currentUser, hasApiKey, logOut } = useAuth();
    const userInitials = currentUser?.email ? currentUser.email.substring(0, 2).toUpperCase() : 'U';

    const [gracePeriod, setGracePeriod] = useState(true);
    useEffect(() => {
        const timer = setTimeout(() => setGracePeriod(false), 3000);
        return () => clearTimeout(timer);
    }, []);

    const qdrantConnected = health?.services?.qdrant === 'connected' || health?.vector_store_connected === true;
    const isHealthLoaded = health !== null;
    const qdrantState = isHealthLoaded ? (qdrantConnected ? 'ready' : 'failed') : (gracePeriod ? 'loading' : 'failed');

    const geminiConnected = health?.status === 'healthy';
    const geminiState = !hasApiKey ? 'no_key' : (isHealthLoaded ? (geminiConnected ? 'ready' : 'failed') : (gracePeriod ? 'loading' : 'failed'));

    const loaded = knowledgeStatus?.project_loaded;

    const getIndicatorUI = (state: string, loadingLabel: string, readyLabel: string, failedLabel: string, noKeyLabel?: string) => {
        if (state === 'loading') {
            return (
                <div className="hidden md:flex items-center gap-1.5 text-xs text-industrial-400">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    {loadingLabel}
                </div>
            );
        }
        if (state === 'no_key') {
            return (
                <div className="hidden md:flex items-center gap-1.5 text-xs text-industrial-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-industrial-300" />
                    <Cpu className="w-3 h-3" />
                    {noKeyLabel}
                </div>
            );
        }
        const isReady = state === 'ready';
        return (
            <div className={`hidden md:flex items-center gap-1.5 text-xs ${isReady ? 'text-industrial-600' : 'text-red-500'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${isReady ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
                <Database className="w-3 h-3" />
                {isReady ? readyLabel : failedLabel}
            </div>
        );
    };

    const getLlmIndicatorUI = (state: string) => {
        if (state === 'loading') {
            return (
                <div className="hidden md:flex items-center gap-1.5 text-xs text-industrial-400">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Checking LLM...
                </div>
            );
        }
        if (state === 'no_key') {
            return (
                <div className="hidden md:flex items-center gap-1.5 text-xs text-industrial-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-industrial-300" />
                    <Cpu className="w-3 h-3" />
                    No Key Configured
                </div>
            );
        }
        const isReady = state === 'ready';
        return (
            <div className={`hidden md:flex items-center gap-1.5 text-xs ${isReady ? 'text-industrial-600' : 'text-red-500'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${isReady ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
                <Cpu className="w-3 h-3" />
                {isReady ? 'Gemini Ready' : 'LLM Offline'}
            </div>
        );
    };


    const greenBadge = "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-semibold bg-green-50 text-green-700 border-green-200";
    const warnBadge = "inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-semibold bg-yellow-50 text-yellow-700 border-yellow-200";

    return (
        <>
            <header className="h-14 bg-white border-b border-industrial-200 flex items-center justify-between px-6 shadow-sm z-10 flex-shrink-0">
                <div className="flex items-center gap-4 min-w-0">
                    <h1 className="text-base font-semibold text-industrial-800 w-[140px] flex-shrink-0 truncate">{title}</h1>
                    <div className="h-4 w-px bg-industrial-200 hidden md:block flex-shrink-0" />

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

                    <Tip text="Your indexed project files are loaded and active.">
                        <div className={`hidden md:flex ${loaded ? greenBadge : warnBadge}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${loaded ? 'bg-green-500' : 'bg-yellow-500'}`} />
                            Project
                        </div>
                    </Tip>
                </div>

                <div className="flex items-center gap-3 flex-shrink-0">
                    <Tip text={geminiState === 'no_key' ? 'No API key configured — go to Settings' : (geminiState === 'failed' ? 'Connection failed' : 'LLM Connected')}>
                        {getLlmIndicatorUI(geminiState)}
                    </Tip>

                    <Tip text={qdrantState === 'failed' ? 'Vector store unreachable' : 'Vector store connected'}>
                        {getIndicatorUI(qdrantState, 'Checking DB...', 'Qdrant Ready', 'DB Down')}
                    </Tip>

                    <Tip text="Refresh connection">
                        <button
                            onClick={handleReconnect}
                            disabled={reconnecting}
                            className="p-1.5 text-industrial-300 hover:text-industrial-600 hover:bg-industrial-100 rounded-full transition-colors disabled:opacity-50"
                        >
                            {reconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                        </button>
                    </Tip>

                    <Tip text="Help & Documentation">
                        <button
                            onClick={() => document.dispatchEvent(new CustomEvent('open-help'))}
                            className="p-1.5 text-industrial-300 hover:text-industrial-600 hover:bg-industrial-100 rounded-full transition-colors font-bold flex items-center justify-center w-7 h-7"
                        >
                            ?
                        </button>
                    </Tip>

                    {/* User Menu */}
                    <div className="relative">
                        <button 
                            onClick={() => setShowUserMenu(!showUserMenu)}
                            className="flex items-center justify-center w-8 h-8 rounded-full bg-industrial-100 border border-industrial-200 text-industrial-700 hover:bg-industrial-200 transition-colors"
                        >
                            {currentUser?.photoURL ? (
                                <img src={currentUser.photoURL} alt="User" className="w-8 h-8 rounded-full" />
                            ) : (
                                <span className="text-xs font-semibold">{userInitials}</span>
                            )}
                        </button>

                        {showUserMenu && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
                                <div className="absolute right-0 mt-2 w-56 bg-white border border-industrial-200 rounded-xl shadow-lg py-1 z-50">
                                    <div className="px-4 py-3 border-b border-industrial-100">
                                        <p className="text-sm font-bold text-industrial-900 truncate">
                                            {currentUser?.displayName || 'User'}
                                        </p>
                                        <p className="text-xs text-industrial-500 truncate mt-0.5">
                                            {currentUser?.email}
                                        </p>
                                    </div>
                                    <div className="p-1.5">
                                        <a href="/settings" onClick={() => setShowUserMenu(false)} className="block px-3 py-2 text-sm text-industrial-700 hover:bg-industrial-50 rounded-lg">
                                            Settings
                                        </a>
                                        <button 
                                            onClick={logOut}
                                            className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg flex items-center gap-2 mt-1"
                                        >
                                            <LogOut className="w-4 h-4" />
                                            Sign Out
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </header>

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
