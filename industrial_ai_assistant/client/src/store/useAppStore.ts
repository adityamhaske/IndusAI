/**
 * useAppStore.ts — Global Zustand store for IndusAI.
 *
 * Project-scoped: each project has its own chat, faults, and analysis state.
 * Persists to localStorage on every write.
 */
import { create } from 'zustand';
import { projectApi } from '../services/projectApi';
import { persist, createJSONStorage } from 'zustand/middleware';

const STORE_KEY = 'indusai_app_state_v2';

interface ChatMessage {
  id: number | string;
  role: 'user' | 'assistant';
  content: string | null;
  structuredResponse?: any;
  timestamp: string;
  projectId?: string;
}

interface AppState {
  // Active Project
  activeProjectId: string;
  switchProject: (pid: string) => void;

  // Chat
  chatHistory: ChatMessage[];
  appendUserMessage: (question: string) => number;
  appendAssistantMessage: (structuredResponse: any) => void;
  clearChat: () => void;
  resetChatSession: () => void;

  // Project knowledge
  knowledgeStatus: any;
  setKnowledgeStatus: (s: any) => void;

  // Fault dataset
  faultDataset: any;
  setFaultDataset: (d: any) => void;
  clearFaultDataset: () => void;

  // Analysis results
  analysisResults: Record<string, any>;
  setAnalysisResult: (rowId: string, result: any) => void;
  clearAnalysisResults: () => void;

  // Selected fault
  selectedFaultId: string | null;
  setSelectedFaultId: (id: string | null) => void;

  // Scope Context
  selectedFiles: string[];
  selectedFolders: string[];
  scopeMode: string;
  setSelectedFiles: (files: string[]) => void;
  setSelectedFolders: (folders: string[]) => void;
  setScopeMode: (mode: string) => void;

  // Project-scoped resets
  resetProjectData: () => void;
  deleteProject: (projectId: string) => Promise<void>;
  resetAll: () => Promise<void>;
}

const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // ── Active Project ─────────────────────────────────────────────
      activeProjectId: localStorage.getItem('activeProjectId') || 'default',

      switchProject(pid: string) {
        localStorage.setItem('activeProjectId', pid);
        set({
          activeProjectId: pid,
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

      // ── Chat ───────────────────────────────────────────────────────
      chatHistory: [],

      appendUserMessage(question: string) {
        const msg: ChatMessage = {
          id: Date.now(),
          role: 'user',
          content: question,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          projectId: get().activeProjectId,
        };
        set(s => ({ chatHistory: [...s.chatHistory, msg] }));
        return msg.id as number;
      },

      appendAssistantMessage(structuredResponse: any) {
        const msg: ChatMessage = {
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

      // ── Project knowledge status ────────────────────────────────
      knowledgeStatus: null,
      setKnowledgeStatus(s: any) { set({ knowledgeStatus: s }); },

      // ── Fault dataset ───────────────────────────────────────────
      faultDataset: null,
      setFaultDataset(d: any) { set({ faultDataset: d }); },
      clearFaultDataset() { set({ faultDataset: null }); },

      // ── Analysis results ────────────────────────────────────────
      analysisResults: {},
      setAnalysisResult(rowId: string, result: any) {
        set(s => ({ analysisResults: { ...s.analysisResults, [rowId]: result } }));
      },
      clearAnalysisResults() { set({ analysisResults: {} }); },

      // ── Selected fault ──────────────────────────────────────────
      selectedFaultId: null,
      setSelectedFaultId(id: string | null) { set({ selectedFaultId: id }); },

      // ── Scope Context ───────────────────────────────────────────
      selectedFiles: [],
      selectedFolders: [],
      scopeMode: 'GLOBAL',
      setSelectedFiles: (files: string[]) => set({ selectedFiles: files }),
      setSelectedFolders: (folders: string[]) => set({ selectedFolders: folders }),
      setScopeMode: (mode: string) => set({ scopeMode: mode }),

      // ── Project-scoped resets ───────────────────────────────────
      resetProjectData() {
        set({
          faultDataset: null,
          analysisResults: {},
          selectedFaultId: null,
        });
      },

      async deleteProject(projectId: string) {
        try {
          await projectApi.deleteProject(projectId);
        } catch { /* ignore */ }
        if (get().activeProjectId === projectId) {
          get().switchProject('default');
        }
      },

      // ── Legacy global reset ─────────────────────────────────────
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
        chatHistory: state.chatHistory.slice(-200),
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
