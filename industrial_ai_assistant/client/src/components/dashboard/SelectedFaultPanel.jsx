import React, { useState } from 'react';
import {
    Cpu, Clock, Activity, Loader2, ChevronDown, ChevronUp,
    CheckCircle, BookOpen, MessageSquare, AlertTriangle, ShieldCheck
} from 'lucide-react';

// ── Confidence badge ──────────────────────────────────────────────────────────
const ConfidenceBadge = ({ level }) => {
    const map = {
        HIGH: 'bg-green-100 text-green-800 border-green-200',
        MEDIUM: 'bg-yellow-100 text-yellow-800 border-yellow-200',
        LOW: 'bg-red-100 text-red-800 border-red-200',
    };
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${map[level] || map.LOW}`}>
            {level}
        </span>
    );
};

const StatRow = ({ label, value, accent }) => (
    <div className="flex items-center justify-between py-1.5 border-b border-industrial-100 last:border-0">
        <span className="text-xs text-industrial-500">{label}</span>
        <span className={`text-xs font-semibold ${accent ? 'text-red-600' : 'text-industrial-800'}`}>{value}</span>
    </div>
);

// ── Expandable source doc card ────────────────────────────────────────────────
const SourceCard = ({ doc }) => {
    const [expanded, setExpanded] = useState(false);
    return (
        <div className="border border-industrial-200 rounded-lg overflow-hidden">
            <button
                onClick={() => setExpanded(v => !v)}
                className="w-full flex items-center justify-between px-3 py-2 bg-industrial-50 hover:bg-industrial-100 text-xs transition-colors"
            >
                <div className="flex items-center gap-2 text-left">
                    <BookOpen className="w-3.5 h-3.5 text-industrial-500 flex-shrink-0" />
                    <div>
                        <span className="font-medium text-industrial-700">
                            {doc.section_title || doc.source_file}
                        </span>
                        {doc.page_number && (
                            <span className="text-industrial-400 ml-1">p.{doc.page_number}</span>
                        )}
                    </div>
                </div>
                {expanded
                    ? <ChevronUp className="w-3.5 h-3.5 text-industrial-400" />
                    : <ChevronDown className="w-3.5 h-3.5 text-industrial-400" />}
            </button>
            {expanded && (
                <div className="px-3 py-2 text-xs text-industrial-600 bg-white leading-relaxed border-t border-industrial-100">
                    {doc.content || 'No content preview available.'}
                </div>
            )}
        </div>
    );
};

// ── Main component ────────────────────────────────────────────────────────────
const SelectedFaultPanel = ({ fault, detail, analysis, analysisError, systemStatus, isAnalyzing, onAnalyze, datasetHash }) => {
    const [question, setQuestion] = useState('');
    const [showAnalysis, setShowAnalysis] = useState(false);

    const llmDown = systemStatus !== null && systemStatus !== undefined && !systemStatus.llm_connected;

    if (!fault) {
        return (
            <div className="bg-white border border-industrial-200 rounded-xl p-6 flex flex-col items-center justify-center h-full text-center text-industrial-400">
                <Activity className="w-10 h-10 mb-3 opacity-50" />
                <p className="text-sm font-medium">Select a fault row to view details</p>
                <p className="text-xs mt-1">Click any row in the table above</p>
            </div>
        );
    }

    const handleAnalyze = async () => {
        await onAnalyze(fault.row_id, datasetHash, question.trim() || null);
        setShowAnalysis(true);
    };

    const isV2 = analysis?.analysis_version === 'v2.0';
    const steps = isV2
        ? (analysis?.diagnostic_steps || [])
        : (analysis?.resolution_steps || []).map(s => (typeof s === 'string' ? s : s?.description));

    return (
        <div className="bg-white border border-industrial-200 rounded-xl overflow-hidden shadow-sm flex flex-col" style={{ maxHeight: '80vh' }}>
            {/* Header */}
            <div className="bg-industrial-800 text-white px-4 py-3 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-industrial-300" />
                    <span className="text-sm font-semibold">Selected Fault</span>
                </div>
                <span className="font-mono text-xs bg-industrial-700 px-2 py-0.5 rounded">{fault.fault_code}</span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* Fault Info */}
                <div className="space-y-1.5">
                    <div className="flex gap-2 items-center">
                        <span className="text-xs text-industrial-400">Row ID:</span>
                        <span className="text-sm font-mono text-industrial-800">#{fault.row_id}</span>
                    </div>
                    <div className="flex gap-2 items-center">
                        <Clock className="w-3.5 h-3.5 text-industrial-400" />
                        <span className="text-xs text-industrial-600">{fault.timestamp}</span>
                    </div>
                    <div className="flex gap-2 items-center">
                        <Cpu className="w-3.5 h-3.5 text-industrial-400" />
                        <span className="text-sm font-medium text-industrial-800">{fault.device}</span>
                    </div>
                    <div className="mt-1 p-2 bg-industrial-50 rounded text-xs text-industrial-700 border border-industrial-100 leading-relaxed">
                        {fault.message}
                    </div>
                </div>

                {/* Stats */}
                {detail && (
                    <div className="border border-industrial-200 rounded-lg p-3">
                        <div className="text-xs font-semibold text-industrial-500 uppercase tracking-wider mb-2">Statistics</div>
                        <StatRow
                            label="Occurrences (last 1h)"
                            value={detail.occurrences_last_hour ?? '—'}
                            accent={(detail.occurrences_last_hour ?? 0) > 5}
                        />
                        <StatRow label="Occurrences (last 24h)" value={detail.occurrences_last_24h ?? '—'} />
                        {detail.top_cooccurring_fault && (
                            <StatRow
                                label="Co-occurring fault (±5min)"
                                value={`${detail.top_cooccurring_fault} ×${detail.cooccurrence_count}`}
                            />
                        )}
                    </div>
                )}

                {/* Custom question */}
                <div className="space-y-2">
                    <label className="flex items-center gap-1.5 text-xs font-semibold text-industrial-600 uppercase tracking-wider">
                        <MessageSquare className="w-3.5 h-3.5" />
                        Ask a specific question (optional)
                    </label>
                    <textarea
                        value={question}
                        onChange={e => setQuestion(e.target.value)}
                        placeholder="e.g. Why does this happen after pallet is lifted?"
                        rows={2}
                        className="w-full text-sm border border-industrial-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none bg-white text-industrial-800 placeholder-industrial-300"
                    />
                    <p className="text-xs text-industrial-400">Leave empty for default fault analysis.</p>
                </div>

                {/* Analyze / Ask button */}
                <button
                    onClick={handleAnalyze}
                    disabled={isAnalyzing || llmDown}
                    title={llmDown ? 'LLM not connected — start Ollama first' : undefined}
                    className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 disabled:cursor-not-allowed text-white py-2.5 rounded-lg text-sm font-medium transition-colors"
                >
                    {isAnalyzing
                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing…</>
                        : question.trim()
                            ? <><MessageSquare className="w-4 h-4" /> Ask AI</>
                            : <><Activity className="w-4 h-4" /> Analyze with AI</>}
                </button>

                {/* LLM-down warning (below button) */}
                {llmDown && (
                    <div className="flex items-start gap-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                        <span className="text-base leading-none flex-shrink-0">⚠️</span>
                        <div>
                            <p className="font-semibold">Local LLM not connected.</p>
                            <p className="text-red-500 mt-0.5">Please ensure Ollama is running: <code className="bg-red-100 px-1 rounded">ollama serve</code></p>
                        </div>
                    </div>
                )}

                {/* Analysis error from backend */}
                {analysisError && (
                    <div className="flex items-start gap-2 text-xs bg-red-50 border border-red-300 rounded-lg px-3 py-2 text-red-800">
                        <span className="text-base leading-none flex-shrink-0">⚠️</span>
                        <div>
                            <p className="font-bold">{analysisError.error_type?.replace(/_/g, ' ')}</p>
                            <p className="text-red-600 mt-0.5">{analysisError.message}</p>
                            {analysisError.action && (
                                <p className="text-red-500 mt-1 font-mono text-xs">{analysisError.action}</p>
                            )}
                        </div>
                    </div>
                )}

                {/* Analysis Result */}
                {analysis && (
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <CheckCircle className="w-4 h-4 text-green-600" />
                                <span className="text-xs font-semibold text-industrial-700">
                                    {isV2 ? 'AI Analysis Complete' : 'Analysis Complete'}
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <ConfidenceBadge level={analysis.confidence} />
                                <button onClick={() => setShowAnalysis(v => !v)} className="text-industrial-400 hover:text-industrial-600">
                                    {showAnalysis ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                </button>
                            </div>
                        </div>

                        {showAnalysis && (
                            <div className="space-y-3 text-sm">
                                {/* User question echo */}
                                {analysis.user_question && (
                                    <div className="text-xs text-industrial-600 bg-industrial-50 rounded px-3 py-2 border border-industrial-200">
                                        <span className="font-semibold text-industrial-700">Q: </span>{analysis.user_question}
                                    </div>
                                )}

                                {/* Summary */}
                                <div className="p-3 bg-blue-50 border border-blue-100 rounded-lg text-xs text-blue-900 leading-relaxed">
                                    {analysis.summary}
                                </div>

                                {/* Likely causes */}
                                {analysis.likely_causes?.length > 0 && (
                                    <div>
                                        <div className="text-xs font-semibold text-industrial-600 mb-1.5 flex items-center gap-1">
                                            <AlertTriangle className="w-3.5 h-3.5 text-orange-500" /> Likely Causes
                                        </div>
                                        <ul className="space-y-1">
                                            {analysis.likely_causes.map((c, i) => (
                                                <li key={i} className="text-xs text-industrial-700 bg-orange-50 rounded px-2 py-1 border border-orange-100 flex gap-2">
                                                    <span className="text-orange-500 font-bold flex-shrink-0">{i + 1}.</span>{c}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {/* Diagnostic steps */}
                                {steps?.length > 0 && (
                                    <div>
                                        <div className="text-xs font-semibold text-industrial-600 mb-1.5">🔧 Diagnostic Steps</div>
                                        <ol className="space-y-1">
                                            {steps.map((s, i) => (
                                                <li key={i} className="text-xs text-industrial-700 flex gap-2">
                                                    <span className="font-bold text-industrial-500 flex-shrink-0">{i + 1}.</span>
                                                    <span>{typeof s === 'string' ? s : s?.description}</span>
                                                </li>
                                            ))}
                                        </ol>
                                    </div>
                                )}

                                {/* Preventive actions */}
                                {isV2 && analysis.preventive_actions?.length > 0 && (
                                    <div>
                                        <div className="text-xs font-semibold text-industrial-600 mb-1.5 flex items-center gap-1">
                                            <ShieldCheck className="w-3.5 h-3.5 text-green-500" /> Preventive Actions
                                        </div>
                                        <ul className="space-y-1">
                                            {analysis.preventive_actions.map((a, i) => (
                                                <li key={i} className="text-xs text-industrial-600 flex gap-2">
                                                    <span className="text-green-500">✓</span>{a}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {/* Documentation sources */}
                                {isV2 && analysis.sources?.length > 0 && (
                                    <div>
                                        <div className="text-xs font-semibold text-industrial-600 mb-1.5 flex items-center gap-1">
                                            <BookOpen className="w-3.5 h-3.5 text-industrial-500" />
                                            Used {analysis.docs_used} documentation source{analysis.docs_used !== 1 ? 's' : ''}
                                        </div>
                                        <div className="space-y-1.5">
                                            {analysis.sources.map((doc, i) => <SourceCard key={i} doc={doc} />)}
                                        </div>
                                    </div>
                                )}

                                {/* No docs retrieved notice */}
                                {isV2 && analysis.docs_used === 0 && (
                                    <div className="text-xs text-industrial-400 bg-industrial-50 rounded px-3 py-2 border border-industrial-200">
                                        📄 No documentation sources retrieved — analysis based on statistics only.
                                    </div>
                                )}

                                {/* Confidence explanation */}
                                {analysis.confidence_explanation && (
                                    <p className="text-xs text-industrial-400 italic border-t border-industrial-100 pt-2">
                                        {analysis.confidence_explanation}
                                    </p>
                                )}

                                {/* Validation warnings */}
                                {analysis.validation_warnings?.length > 0 && (
                                    <div className="text-xs text-orange-600 bg-orange-50 rounded p-2 border border-orange-100">
                                        ⚠ {analysis.validation_warnings.join(' ')}
                                    </div>
                                )}

                                {/* Footer metadata */}
                                <div className="text-xs text-industrial-400 flex flex-wrap gap-2 border-t border-industrial-100 pt-2">
                                    <span>{analysis.analysis_version}</span>
                                    <span>·</span>
                                    <span>LLM: {analysis.llm_latency_ms?.toFixed(0)}ms</span>
                                    {isV2 && <><span>·</span><span>RAG: {analysis.rag_latency_ms?.toFixed(0)}ms</span></>}
                                    <span>·</span>
                                    <span title={analysis.dataset_hash}>hash: {analysis.dataset_hash?.slice(0, 8)}</span>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default SelectedFaultPanel;
