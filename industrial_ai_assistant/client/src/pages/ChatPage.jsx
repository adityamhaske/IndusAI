import React, { useRef, useEffect, useCallback } from 'react';
import { Loader2, Zap, Database, AlertTriangle } from 'lucide-react';
import { queryKnowledge, getProjectStatus } from '../services/knowledgeApi';
import useAppStore from '../store/useAppStore';
import AnswerCard from '../components/chat/AnswerCard';
import ProjectExplorer from '../components/chat/ProjectExplorer';

import { Link } from 'react-router-dom';

// ── Knowledge Mode Badge ───────────────────────────────────────────────────────
const KnowledgeBadge = ({ status }) => {
    if (!status) return null;
    if (status.project_loaded) {
        const folder = status.folder?.split('/').pop() || 'Project';
        return (
            <div className="flex items-center gap-2 text-xs bg-green-50 border border-green-200 text-green-700 px-3 py-1.5 rounded-full font-medium">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <Database className="w-3 h-3" />
                Project Knowledge Active · {folder}
                <span className="text-green-500 font-normal">({status.tags_indexed?.toLocaleString()} tags)</span>
            </div>
        );
    }
    return (
        <div className="flex items-center gap-2 text-xs bg-yellow-50 border border-yellow-200 text-yellow-700 px-3 py-1.5 rounded-full font-medium">
            <span className="w-2 h-2 rounded-full bg-yellow-500" />
            General Documentation Mode —{' '}
            <Link to="/project" className="underline hover:text-yellow-800">Index a project</Link>
        </div>
    );
};

// ── Chat Message ───────────────────────────────────────────────────────────────
const Message = ({ msg }) => {
    const isUser = msg.role === 'user';
    return (
        <div className={`p-5 border-b border-industrial-100 ${isUser ? 'bg-white' : 'bg-industrial-50'}`}>
            <div className="flex items-start gap-3 max-w-3xl mx-auto">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5 ${isUser ? 'bg-primary-600 text-white' : 'bg-industrial-200 text-industrial-600'
                    }`}>
                    {isUser ? 'U' : 'AI'}
                </div>
                <div className="flex-1 min-w-0">
                    {/* Structured AI response */}
                    {!isUser && msg.structuredResponse ? (
                        <AnswerCard data={msg.structuredResponse} />
                    ) : (
                        /* Plain text (user messages or error strings) */
                        <p className="text-sm text-industrial-800 leading-relaxed whitespace-pre-wrap">
                            {msg.content}
                        </p>
                    )}
                    <p className="text-[10px] text-industrial-300 mt-2">{msg.timestamp}</p>
                </div>
            </div>
        </div>
    );
};

// ── Scope Controls (Compact Chip) ──────────────────────────────────────────────
const ScopeChip = () => {
    const selectedFiles = useAppStore(s => s.selectedFiles);
    const selectedFolders = useAppStore(s => s.selectedFolders);
    const scopeMode = useAppStore(s => s.scopeMode);
    const setScopeMode = useAppStore(s => s.setScopeMode);

    const count = selectedFiles.length + selectedFolders.length;

    return (
        <div className="px-5 pt-3 flex items-center gap-3 flex-wrap">
            {count > 0 && (
                <div className="flex items-center gap-1.5 text-xs bg-primary-50 border border-primary-200 text-primary-700 px-2.5 py-1 rounded-full shrink-0">
                    <Database className="w-3 h-3" />
                    <span className="font-medium">Scoped to {count} item{count !== 1 && 's'}</span>
                </div>
            )}

            <div className="flex items-center gap-1.5 shrink-0 bg-industrial-100 rounded-full px-2 py-1">
                <span className="text-[10px] font-bold text-industrial-500 uppercase tracking-wider pl-1">Mode:</span>
                <select
                    value={scopeMode}
                    onChange={e => setScopeMode(e.target.value)}
                    className="text-xs border-0 bg-transparent text-industrial-700 hover:text-industrial-900 outline-none cursor-pointer font-medium p-0 focus:ring-0"
                >
                    <option value="GLOBAL">GLOBAL</option>
                    <option value="PREFER">PREFER</option>
                    <option value="STRICT">STRICT</option>
                </select>
            </div>

            {scopeMode === 'STRICT' && count === 0 && (
                <div className="text-xs text-red-600 flex items-center gap-1 font-medium ml-1">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Select files for STRICT mode
                </div>
            )}
            {count > 100 && (
                <div className="text-xs text-orange-600 flex items-center gap-1 font-medium ml-1">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Large selection may slow search
                </div>
            )}
        </div>
    );
};

// ── Input Bar ──────────────────────────────────────────────────────────────────
const InputBar = ({ onSend, disabled }) => {
    const [text, setText] = React.useState('');
    const submit = () => {
        const q = text.trim();
        if (!q || disabled) return;
        onSend(q);
        setText('');
    };
    return (
        <div className="p-4 flex gap-3">
            <input
                className="flex-1 border border-industrial-200 rounded-xl px-4 py-3 text-sm text-industrial-800 placeholder-industrial-300 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-200 bg-white"
                placeholder={disabled ? 'Generating response…' : 'Ask about your PLC project, tags, routines, IO, faults…'}
                value={text}
                onChange={e => setText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
                disabled={disabled}
            />
            <button
                onClick={submit}
                disabled={disabled || !text.trim()}
                className="px-5 py-3 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
                {disabled ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                {disabled ? '…' : 'Send'}
            </button>
        </div>
    );
};

// ── ChatPage ───────────────────────────────────────────────────────────────────
const ChatPage = () => {
    // All state lives in the global Zustand store — survives page navigation
    const chatHistory = useAppStore(s => s.chatHistory);
    const appendUserMessage = useAppStore(s => s.appendUserMessage);
    const appendAssistantMessage = useAppStore(s => s.appendAssistantMessage);
    const knowledgeStatus = useAppStore(s => s.knowledgeStatus);
    const setKnowledgeStatus = useAppStore(s => s.setKnowledgeStatus);
    const selectedFiles = useAppStore(s => s.selectedFiles);
    const selectedFolders = useAppStore(s => s.selectedFolders);
    const scopeMode = useAppStore(s => s.scopeMode);

    const [isLoading, setIsLoading] = React.useState(false);
    const bottomRef = useRef(null);

    // Fetch project status once on mount (not on every render)
    useEffect(() => {
        if (!knowledgeStatus) {
            getProjectStatus('default')
                .then(setKnowledgeStatus)
                .catch(() => { });
        }
    }, []); // intentionally empty — only run once

    // Auto-scroll
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatHistory]);

    const handleSend = useCallback(async (question) => {
        appendUserMessage(question);
        setIsLoading(true);
        try {
            const data = await queryKnowledge({
                question,
                project_id: 'default',
                selected_files: selectedFiles,
                selected_folders: selectedFolders,
                scope_mode: scopeMode
            });

            // Parse summary if it's still a JSON string (backward-compat)
            let structured = { ...data };
            if (typeof data.summary === 'string' && data.summary.trim().startsWith('{')) {
                try {
                    const inner = JSON.parse(data.summary);
                    structured = {
                        ...data,
                        summary: inner.summary || data.summary,
                        root_causes: inner.root_causes || data.root_causes || [],
                        recommended_actions: inner.recommended_actions || data.recommended_actions || [],
                        supporting_evidence: inner.supporting_evidence || data.supporting_evidence || [],
                        limitations: inner.limitations || data.limitations || [],
                    };
                } catch { /* use data as-is */ }
            }

            appendAssistantMessage(structured);
        } catch (err) {
            const errData = err.data || {};
            const isNotIndexed = errData.error_type === 'PROJECT_NOT_INDEXED';
            appendAssistantMessage(
                isNotIndexed
                    ? `🔴 No project indexed. Go to Settings → Index your project folder first.\n\nDetected tags: ${(errData.detected_tags || []).join(', ')}`
                    : `⚠️ AI service is currently unable to process your request. Please check provider configuration in Settings.`
            );
        } finally {
            setIsLoading(false);
        }
    }, [appendUserMessage, appendAssistantMessage]);

    // Show welcome message if no history
    const showWelcome = chatHistory.length === 0;

    const isStrictInvalid = scopeMode === 'STRICT' && (selectedFiles.length + selectedFolders.length) === 0;

    return (
        <div className="flex flex-row h-full overflow-hidden bg-industrial-50">
            <div className="flex-1 flex flex-col min-w-0 h-full">
                {/* Knowledge mode banner */}
                <div className="bg-white border-b border-industrial-200 px-6 py-2.5 flex items-center gap-3 flex-shrink-0">
                    <KnowledgeBadge status={knowledgeStatus} />
                </div>

                {/* Messages */}
                <div className="flex-1 overflow-y-auto min-h-0">
                    <div className="max-w-4xl mx-auto w-full bg-white shadow-sm min-h-full border-x border-industrial-200 flex flex-col">
                        {showWelcome && (
                            <div className="p-5 border-b border-industrial-100 bg-industrial-50">
                                <div className="flex items-start gap-3 max-w-3xl mx-auto">
                                    <div className="w-7 h-7 rounded-full bg-industrial-200 text-industrial-600 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">AI</div>
                                    <div>
                                        <p className="text-sm text-industrial-700 leading-relaxed">
                                            Hello. Ask me anything about your PLC system — tags, routines, IO maps, fault logic, or commissioning status.
                                            {!knowledgeStatus?.project_loaded && (
                                                <span className="text-yellow-600"> Index a project folder in <a href="/settings" className="underline hover:text-yellow-800">Settings</a> for project-level answers.</span>
                                            )}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )}
                        {chatHistory.map((msg) => <Message key={msg.id} msg={msg} />)}
                        {isLoading && (
                            <div className="p-5 bg-industrial-50 border-b border-industrial-100">
                                <div className="flex items-start gap-3 max-w-3xl mx-auto">
                                    <div className="w-7 h-7 rounded-full bg-industrial-200 text-industrial-600 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">AI</div>
                                    <div className="flex-1 space-y-3">
                                        <div className="flex items-center gap-2 text-sm text-industrial-500">
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                            <span>Searching knowledge base…</span>
                                        </div>
                                        {/* Shimmer skeleton */}
                                        <div className="space-y-2 animate-pulse">
                                            <div className="h-4 bg-industrial-200 rounded w-3/4" />
                                            <div className="h-4 bg-industrial-200 rounded w-full" />
                                            <div className="h-4 bg-industrial-200 rounded w-5/6" />
                                            <div className="h-3 bg-industrial-100 rounded w-1/2 mt-3" />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                        <div ref={bottomRef} className="pb-4" />
                    </div>
                </div>

                {/* Input */}
                <div className="bg-white border-t border-industrial-200 flex-shrink-0">
                    <div className="max-w-4xl mx-auto w-full border-x border-industrial-200">
                        {knowledgeStatus?.project_loaded && <ScopeChip />}
                        <InputBar onSend={handleSend} disabled={isLoading || isStrictInvalid} />
                    </div>
                </div>
            </div>

            {/* Project Explorer Drawer on Right */}
            {knowledgeStatus?.project_loaded && <ProjectExplorer />}
        </div>
    );
};

export default ChatPage;
