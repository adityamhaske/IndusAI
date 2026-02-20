/**
 * useAppStore.js — Global Zustand store for IndusAI.
 *
 * Persists to localStorage on every write.
 * Hydrates on app load automatically.
 * Clears only when resetAll() is explicitly called.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

const STORE_KEY = 'indusai_app_state_v1';

const useAppStore = create(
    persist(
        (set, get) => ({
            // ── Chat ─────────────────────────────────────────────────────────
            chatHistory: [],   // [{ id, role, content, structuredResponse, timestamp }]

            appendUserMessage(question) {
                const msg = {
                    id: Date.now(),
                    role: 'user',
                    content: question,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                };
                set(s => ({ chatHistory: [...s.chatHistory, msg] }));
                return msg.id;
            },

            appendAssistantMessage(structuredResponse) {
                const msg = {
                    id: Date.now() + 1,
                    role: 'assistant',
                    // plain text fallback for errors / strings
                    content: typeof structuredResponse === 'string' ? structuredResponse : null,
                    structuredResponse: typeof structuredResponse === 'object' ? structuredResponse : null,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                };
                set(s => ({ chatHistory: [...s.chatHistory, msg] }));
            },

            clearChat() {
                set({ chatHistory: [] });
            },

            // ── Project knowledge status ──────────────────────────────────
            knowledgeStatus: null,   // ProjectStatus from backend
            setKnowledgeStatus(s) { set({ knowledgeStatus: s }); },

            // ── Fault dataset ─────────────────────────────────────────────
            faultDataset: null,      // { file, uploadedAt, summary, rows }
            setFaultDataset(d) { set({ faultDataset: d }); },
            clearFaultDataset() { set({ faultDataset: null }); },

            // ── Analysis results ──────────────────────────────────────────
            analysisResults: {},     // { [rowId]: AnalysisResponse }
            setAnalysisResult(rowId, result) {
                set(s => ({ analysisResults: { ...s.analysisResults, [rowId]: result } }));
            },
            clearAnalysisResults() { set({ analysisResults: {} }); },

            // ── Selected fault ────────────────────────────────────────────
            selectedFaultId: null,
            setSelectedFaultId(id) { set({ selectedFaultId: id }); },

            // ── Global reset ──────────────────────────────────────────────
            async resetAll() {
                // Reset backend project index
                try {
                    await fetch('/api/project/reset?project_id=default', { method: 'DELETE' });
                } catch { /* ignore */ }
                // Clear frontend state
                set({
                    chatHistory: [],
                    knowledgeStatus: null,
                    faultDataset: null,
                    analysisResults: {},
                    selectedFaultId: null,
                });
            },
        }),
        {
            name: STORE_KEY,
            storage: createJSONStorage(() => localStorage),
            // Persist everything except transient UI state
            partialize: (state) => ({
                chatHistory: state.chatHistory.slice(-100), // cap at 100 messages
                knowledgeStatus: state.knowledgeStatus,
                faultDataset: state.faultDataset,
                analysisResults: state.analysisResults,
                selectedFaultId: state.selectedFaultId,
            }),
        }
    )
);

export default useAppStore;
