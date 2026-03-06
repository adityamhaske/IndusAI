/**
 * useAppStore.js — Global Zustand store for IndusAI.
 *
 * Project-scoped: each project has its own chat, faults, and analysis state.
 * Persists to localStorage on every write.
 * Hydrates on app load automatically.
 */
import { create } from 'zustand';
import { projectApi } from '../services/projectApi';
import { persist, createJSONStorage } from 'zustand/middleware';

const STORE_KEY = 'indusai_app_state_v2';

const useAppStore = create(
    persist(
        (set, get) => ({
            // ── Active Project ───────────────────────────────────────────────
            activeProjectId: localStorage.getItem('activeProjectId') || 'default',

            switchProject(pid) {
                localStorage.setItem('activeProjectId', pid);
                set({
                    activeProjectId: pid,
                    // Clear transient state on switch — project-specific data reloads from backend
                    chatHistory: [],
                    faultDataset: null,
                    analysisResults: {},
                    selectedFaultId: null,
                    selectedFiles: [],
                    selectedFolders: [],
                    scopeMode: 'GLOBAL',
                    knowledgeStatus: null,
                });
            },

            // ── Chat ─────────────────────────────────────────────────────────
            chatHistory: [],   // [{ id, role, content, structuredResponse, timestamp, projectId }]

            appendUserMessage(question) {
                const msg = {
                    id: Date.now(),
                    role: 'user',
                    content: question,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    projectId: get().activeProjectId,
                };
                set(s => ({ chatHistory: [...s.chatHistory, msg] }));
                return msg.id;
            },

            appendAssistantMessage(structuredResponse) {
                const msg = {
                    id: Date.now() + 1,
                    role: 'assistant',
                    content: typeof structuredResponse === 'string' ? structuredResponse : null,
                    structuredResponse: typeof structuredResponse === 'object' ? structuredResponse : null,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    projectId: get().activeProjectId,
                };
                set(s => ({ chatHistory: [...s.chatHistory, msg] }));
            },

            clearChat() {
                // Only clears chat for the active project
                const pid = get().activeProjectId;
                set(s => ({ chatHistory: s.chatHistory.filter(m => m.projectId && m.projectId !== pid) }));
            },

            resetChatSession() {
                const pid = get().activeProjectId;
                set(s => ({
                    chatHistory: s.chatHistory.filter(m => m.projectId && m.projectId !== pid),
                    selectedFiles: [],
                    selectedFolders: [],
                    scopeMode: 'GLOBAL',
                }));
            },

            // ── Project knowledge status ──────────────────────────────────
            knowledgeStatus: null,
            setKnowledgeStatus(s) { set({ knowledgeStatus: s }); },

            // ── Fault dataset ─────────────────────────────────────────────
            faultDataset: null,
            setFaultDataset(d) { set({ faultDataset: d }); },
            clearFaultDataset() { set({ faultDataset: null }); },

            // ── Analysis results ──────────────────────────────────────────
            analysisResults: {},
            setAnalysisResult(rowId, result) {
                set(s => ({ analysisResults: { ...s.analysisResults, [rowId]: result } }));
            },
            clearAnalysisResults() { set({ analysisResults: {} }); },

            // ── Selected fault ────────────────────────────────────────────
            selectedFaultId: null,
            setSelectedFaultId(id) { set({ selectedFaultId: id }); },

            // ── Scope Context ─────────────────────────────────────────────
            selectedFiles: [],
            selectedFolders: [],
            scopeMode: 'GLOBAL',
            setSelectedFiles: (files) => set({ selectedFiles: files }),
            setSelectedFolders: (folders) => set({ selectedFolders: folders }),
            setScopeMode: (mode) => set({ scopeMode: mode }),

            // ── Project-scoped resets ─────────────────────────────────────
            resetProjectData() {
                // Clear fault data + analysis for the active project
                set({
                    faultDataset: null,
                    analysisResults: {},
                    selectedFaultId: null,
                });
            },

            async deleteProject(projectId) {
                try {
                    await projectApi.deleteProject(projectId);
                } catch { /* ignore */ }
                // If we deleted the active project, switch to default
                if (get().activeProjectId === projectId) {
                    get().switchProject('default');
                }
            },

            // ── Legacy global reset (kept for backward compatibility) ─────
            async resetAll() {
                try {
                    await projectApi.resetProject('default');
                } catch { /* ignore */ }
                set({
                    chatHistory: [],
                    knowledgeStatus: null,
                    faultDataset: null,
                    analysisResults: {},
                    selectedFaultId: null,
                    selectedFiles: [],
                    selectedFolders: [],
                    scopeMode: 'GLOBAL',
                    activeProjectId: 'default',
                });
                localStorage.setItem('activeProjectId', 'default');
            },
        }),
        {
            name: STORE_KEY,
            storage: createJSONStorage(() => localStorage),
            partialize: (state) => ({
                activeProjectId: state.activeProjectId,
                chatHistory: state.chatHistory.slice(-200), // cap at 200 messages across projects
                knowledgeStatus: state.knowledgeStatus,
                faultDataset: state.faultDataset,
                analysisResults: state.analysisResults,
                selectedFaultId: state.selectedFaultId,
                selectedFiles: state.selectedFiles,
                selectedFolders: state.selectedFolders,
                scopeMode: state.scopeMode,
            }),
        }
    )
);

export default useAppStore;
