import React, { useState, useEffect } from 'react';
import {
    Cpu, Clock, Activity, Loader2, ChevronDown, ChevronUp,
    MessageSquare, AlertTriangle, X, PlayCircle
} from 'lucide-react';
import { faultApi } from '../../services/faultApi';

const TrendIndicator = ({ trend }) => {
    switch (trend) {
        case 'RISING':
            return <span className="text-amber-600 font-bold">↑ RISING</span>;
        case 'DECLINING':
            return <span className="text-green-600 font-bold">↓ DECLINING</span>;
        default:
            return <span className="text-industrial-500 font-bold">− STABLE</span>;
    }
};

const StatStrip = ({ fault, evidence, confidence }) => {
    return (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-industrial-200 border border-industrial-200 rounded-lg overflow-hidden font-mono text-xs shadow-sm">
            <div className="bg-industrial-50 p-2 flex flex-col justify-center">
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">Fault</span>
                <span className="font-semibold text-industrial-800">{fault.fault_code}</span>
            </div>
            <div className="bg-industrial-50 p-2 flex flex-col justify-center">
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">1H Vol</span>
                <span className="font-semibold text-industrial-800">{evidence?.occurrences_1h ?? 'N/A'}</span>
            </div>
            <div className="bg-industrial-50 p-2 flex flex-col justify-center">
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">24H Vol</span>
                <span className="font-semibold text-industrial-800">{evidence?.occurrences_24h ?? 'N/A'}</span>
            </div>
            <div className={`p-2 flex flex-col justify-center ${evidence?.burst_detected ? 'bg-red-50 text-red-700' : 'bg-industrial-50 text-industrial-800'}`}>
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">Burst</span>
                <span className="font-semibold">
                    {evidence?.burst_detected ? `YES (${evidence.burst_count} events)` : 'NO'}
                </span>
            </div>
            <div className="bg-industrial-50 p-2 flex flex-col justify-center">
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">Co-Occurrence</span>
                <span className="font-semibold text-industrial-800 truncate" title={evidence?.co_occurrence?.[0] ? `${evidence.co_occurrence[0].fault}` : ''}>
                    {evidence?.top_cooccurring_fault ? `${evidence.top_cooccurring_fault} (x${evidence.cooccurrence_count})` :
                        (evidence?.co_occurrence?.[0] ? `${evidence.co_occurrence[0].fault} (x${evidence.co_occurrence[0].count})` : 'NONE')}
                </span>
            </div>
            <div className="bg-industrial-50 p-2 flex flex-col justify-center">
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">Trend</span>
                <TrendIndicator trend={evidence?.trend} />
            </div>
            <div className="bg-industrial-50 p-2 flex flex-col justify-center col-span-2 md:col-span-3">
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">Anomaly Score</span>
                <div className="flex items-center gap-2">
                    <div className="flex-1 bg-industrial-200 h-1.5 rounded-full overflow-hidden">
                        <div
                            className={`h-full ${evidence?.anomaly_score > 2 ? 'bg-red-500' : evidence?.anomaly_score > 1 ? 'bg-amber-500' : 'bg-green-500'}`}
                            style={{ width: `${Math.min((evidence?.anomaly_score || 0) * 20, 100)}%` }}
                        ></div>
                    </div>
                    <span className="font-semibold text-industrial-800 text-[10px]">{evidence?.anomaly_score?.toFixed(2)}x</span>
                </div>
            </div>
        </div>
    );
};

const SelectedFaultPanel = ({ fault, detail, analysis, analysisError, systemStatus, isAnalyzing, onAnalyze, datasetHash, onClose }) => {
    const [question, setQuestion] = useState('');
    const [showEvidence, setShowEvidence] = useState(false);

    // Dual Engine State
    const [quickStats, setQuickStats] = useState(null);
    const [isFetchingStats, setIsFetchingStats] = useState(false);
    const [statsError, setStatsError] = useState(null);

    const llmDown = systemStatus !== null && systemStatus !== undefined && !systemStatus.llm_connected;

    // Auto-trigger stats & analysis on fault selection
    useEffect(() => {
        if (!fault) return;
        let isMounted = true;

        const fetchDualEngine = async () => {
            // 1. Instant Statistical Engine
            setIsFetchingStats(true);
            setStatsError(null);
            setQuickStats(null);
            try {
                // If the backend has a bug and doesn't find defaults, we pass 'default'
                const stats = await faultApi.quickStats(fault.row_id, 'default');
                if (isMounted) setQuickStats(stats);
            } catch (err) {
                if (isMounted) setStatsError(err.response?.data?.message || err.message || 'Failed to fetch quick stats');
            } finally {
                if (isMounted) setIsFetchingStats(false);
            }

            // 2. Async AI Analysis (if Ollama is up and we haven't already got an analysis error)
            if (isMounted && !isAnalyzing && !analysis && !analysisError && !llmDown) {
                // We use setTimeout to let State 1 (stats) render before triggering blocking operations if any
                setTimeout(() => {
                    if (isMounted) {
                        onAnalyze(fault.row_id, datasetHash, null);
                    }
                }, 50);
            }
        };

        const t = setTimeout(fetchDualEngine, 300); // 300ms debounce
        return () => { isMounted = false; clearTimeout(t); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fault?.row_id]);


    if (!fault) return null;

    const handleAnalyze = async () => {
        await onAnalyze(fault.row_id, datasetHash, question.trim() || null);
    };

    const isAnalyzed = !!analysis;
    const statsObj = quickStats || analysis?.statistics;

    // Check integrity from analysis or quick stats
    const isIntegrityFailure = analysis?.statistics?.integrity_passed === false || quickStats?.integrity_passed === false;
    const isParseFailed = analysis?.fault_summary?.startsWith('[STRUCTURED PARSE FAILED - RAW OUTPUT]');
    const displaySummary = isParseFailed ? analysis.fault_summary.replace('[STRUCTURED PARSE FAILED - RAW OUTPUT]\n', '') : analysis?.fault_summary;

    return (
        <div className="bg-white flex flex-col h-full w-full shadow-2xl absolute right-0 top-0 bottom-0 z-50">
            {/* Header */}
            <div className="bg-industrial-900 text-white px-5 py-4 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-industrial-400" />
                    <span className="text-sm font-semibold tracking-wide">DIAGNOSTIC INSTRUMENT</span>
                </div>
                <button
                    onClick={onClose}
                    className="p-1 text-industrial-400 hover:text-white hover:bg-industrial-700 rounded transition-colors"
                >
                    <X className="w-5 h-5" />
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 pb-8">

                {/* Common Target Metadata */}
                <div className="space-y-4 mb-6">
                    <div>
                        <h3 className="text-xs font-semibold text-industrial-500 uppercase tracking-wider mb-1">Target</h3>
                        <div className="text-xl font-bold font-mono text-industrial-900">{fault.fault_code}</div>
                        <div className="text-sm text-industrial-600 mt-1 leading-snug">{fault.message}</div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 border-y border-industrial-100 py-4">
                        <div>
                            <div className="text-xs text-industrial-400 mb-1 flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Timestamp</div>
                            <div className="text-sm font-medium text-industrial-800">{fault.timestamp}</div>
                        </div>
                        <div>
                            <div className="text-xs text-industrial-400 mb-1 flex items-center gap-1.5"><Cpu className="w-3.5 h-3.5" /> Device</div>
                            <div className="text-sm font-medium text-industrial-800">{fault.device}</div>
                        </div>
                    </div>
                </div>

                {/* DUAL ENGINE FRAMEWORK */}

                {/* ENGINE 1: STATISTICAL (Instant) */}
                <div className="mb-6">
                    <h2 className="text-[11px] font-bold text-industrial-500 flex items-center gap-1.5 uppercase tracking-widest border-b border-industrial-100 pb-2 mb-3">
                        <Activity className="w-4 h-4 text-primary-600" /> Statistical Engine
                    </h2>

                    {isFetchingStats ? (
                        <div className="animate-pulse flex space-x-4 bg-industrial-50 p-4 rounded-lg border border-industrial-100">
                            <div className="flex-1 space-y-3 py-1">
                                <div className="h-3 bg-industrial-200 rounded w-1/4"></div>
                                <div className="space-y-2 pt-2">
                                    <div className="h-10 bg-industrial-200 rounded"></div>
                                </div>
                            </div>
                        </div>
                    ) : statsError ? (
                        <div className="text-xs text-red-600 bg-red-50 border border-red-200 p-3 rounded-lg">
                            <strong>Statistical Engine Error:</strong> {statsError}
                        </div>
                    ) : statsObj ? (
                        <div className="animate-fade-in space-y-3">
                            <StatStrip fault={fault} evidence={statsObj} confidence={statsObj.confidence} />

                            {/* INTEGRITY FAILURE OVERRIDE */}
                            {isIntegrityFailure && (
                                <div className="bg-red-50 border border-red-200 p-4 rounded-lg shadow-sm">
                                    <h3 className="text-[11px] font-bold text-red-700 uppercase tracking-widest flex items-center gap-1.5 mb-2">
                                        <AlertTriangle className="w-4 h-4" /> DATA INTEGRITY WARNING
                                    </h3>
                                    <p className="text-sm text-red-900 leading-snug">
                                        The statistical engine detected contradictions in the event log (e.g., Burst recorded without sufficient hourly volume).
                                        <strong> Please review manually.</strong>
                                    </p>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="text-xs text-industrial-400 italic">No statistical data available.</div>
                    )}
                </div>

                {/* ENGINE 2: AI ANALYSIS (Async) */}
                <div className="mb-4">
                    <h2 className="text-[11px] font-bold text-industrial-500 flex items-center gap-1.5 uppercase tracking-widest border-b border-industrial-100 pb-2 mb-4">
                        <Cpu className="w-4 h-4 text-primary-600" /> AI Analysis
                    </h2>

                    {isAnalyzing ? (
                        <div className="flex flex-col items-center justify-center py-10 bg-industrial-50 border border-industrial-100 rounded-lg text-industrial-400 space-y-4">
                            <Loader2 className="w-8 h-8 animate-spin text-industrial-600" />
                            <div className="text-sm font-medium animate-pulse">Running reasoning models...</div>
                        </div>
                    ) : isAnalyzed ? (
                        <div className="space-y-5 animate-fade-in">
                            {/* 1. Fault Summary */}
                            <div className="space-y-2">
                                <h3 className="text-[10px] font-bold text-industrial-400 uppercase tracking-widest flex justify-between items-center">
                                    <span>Fault Summary</span>
                                    <div className="flex gap-2">
                                        {isParseFailed && (
                                            <span className="px-1.5 rounded bg-amber-100 text-amber-700 font-bold border border-amber-200">
                                                RAW OUTPUT
                                            </span>
                                        )}
                                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${analysis.confidence === 'HIGH' || analysis.confidence === 'VERY_HIGH' ? 'bg-green-100 text-green-700' :
                                            analysis.confidence === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'
                                            }`}>
                                            CONFIDENCE: {analysis.confidence}
                                        </span>
                                    </div>
                                </h3>
                                {isParseFailed ? (
                                    <div className="bg-amber-50 rounded p-3 border border-amber-200 text-amber-900 text-sm font-mono whitespace-pre-wrap">
                                        {displaySummary}
                                    </div>
                                ) : (
                                    <p className="text-sm font-medium text-industrial-900 leading-snug">
                                        {displaySummary}
                                    </p>
                                )}
                            </div>

                            {!isParseFailed && (
                                <>
                                    {/* 2. Root Cause */}
                                    <div className="space-y-1">
                                        <h3 className="text-[10px] font-bold text-industrial-400 uppercase tracking-widest">
                                            Root Cause
                                        </h3>
                                        <p className="text-sm text-industrial-800 leading-snug">
                                            {analysis.root_cause}
                                        </p>
                                    </div>

                                    {/* 3. Trigger Mechanism */}
                                    <div className="space-y-1">
                                        <h3 className="text-[10px] font-bold text-industrial-400 uppercase tracking-widest">
                                            Trigger Mechanism
                                        </h3>
                                        <p className="text-sm text-industrial-800 leading-snug">
                                            {analysis.trigger_mechanism}
                                        </p>
                                    </div>

                                    {/* 4. Resolution Steps */}
                                    <div className="bg-industrial-900 text-white rounded-lg p-4 shadow-sm border border-industrial-800 space-y-3">
                                        <h3 className="text-[10px] font-bold text-industrial-400 uppercase tracking-widest flex items-center gap-1.5">
                                            <PlayCircle className="w-3 h-3 text-primary-400" /> Resolution Steps
                                        </h3>
                                        <ul className="text-sm font-medium leading-relaxed space-y-2">
                                            {Array.isArray(analysis.resolution_steps) ? (
                                                analysis.resolution_steps.map((step, idx) => (
                                                    <li key={idx} className="flex items-start gap-2">
                                                        <span className="text-primary-400 font-bold">{idx + 1}.</span>
                                                        <span className="flex-1">{step}</span>
                                                    </li>
                                                ))
                                            ) : (
                                                <li>{analysis.resolution_steps}</li>
                                            )}
                                        </ul>
                                    </div>
                                </>
                            )}



                            {/* Footer info */}
                            <div className="pt-2 flex justify-end">
                                <span className="text-[10px] text-industrial-400 font-mono tracking-wider">
                                    SYS_{analysis.analysis_version} • {analysis.total_latency_ms?.toFixed(0)}MS
                                </span>
                            </div>

                        </div>
                    ) : (
                        <div className="space-y-4">
                            <div className="bg-industrial-50 border border-industrial-100 p-4 rounded-lg flex flex-col items-center justify-center text-center space-y-3">
                                <div className="text-sm text-industrial-600 font-medium">Ready for AI Deep Dive</div>
                                <p className="text-xs text-industrial-500 px-4">
                                    The Statistical Engine has computed deterministic metrics. Run AI inference for root cause analysis and action instructions if needed.
                                </p>
                                <button
                                    onClick={handleAnalyze}
                                    disabled={llmDown}
                                    className="w-full max-w-[200px] flex items-center justify-center gap-2 bg-industrial-900 hover:bg-black disabled:bg-industrial-300 text-white py-2.5 rounded-lg text-sm font-semibold transition-colors"
                                >
                                    <Activity className="w-4 h-4" />
                                    START AI INFERENCE
                                </button>
                            </div>

                            {llmDown && (
                                <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-md p-3">
                                    <strong>System Offline:</strong> LLM connection failed. Start Ollama to proceed.
                                </div>
                            )}
                            {analysisError && (
                                <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-md p-3">
                                    <strong>Error:</strong> {
                                        (analysisError.message || '').includes("Provider") && (analysisError.message || '').includes("is not configured")
                                            ? "Selected AI provider is not activated. Please verify API key and provider configuration in Settings."
                                            : analysisError.message || 'Analysis failed'
                                    }
                                </div>
                            )}
                        </div>
                    )}

                    {/* ALWAYS VISIBLE: Custom Directive Form */}
                    {!isAnalyzing && (
                        <div className="mt-4 pt-4 border-t border-industrial-100 space-y-3">
                            <label className="text-[10px] font-bold text-industrial-500 uppercase tracking-widest">
                                {isAnalyzed ? "Follow-up Directive" : "Ask Custom Query"}
                            </label>
                            <div className="flex gap-2">
                                <textarea
                                    value={question}
                                    onChange={e => setQuestion(e.target.value)}
                                    placeholder="Ask a specific question about this fault..."
                                    rows={1}
                                    className="flex-1 text-sm border border-industrial-200 rounded-lg px-3 py-2 flex items-center focus:outline-none focus:ring-1 focus:ring-industrial-500 resize-none bg-industrial-50 text-industrial-900"
                                />
                                <button
                                    onClick={handleAnalyze}
                                    disabled={llmDown || !question.trim()}
                                    className="px-4 bg-industrial-900 hover:bg-black disabled:bg-industrial-300 text-white rounded-lg text-sm font-semibold transition-colors flex items-center justify-center whitespace-nowrap"
                                >
                                    <PlayCircle className="w-4 h-4 ml-1" />
                                </button>
                            </div>
                            {llmDown && (
                                <div className="text-[11px] text-red-600 font-medium mt-1">
                                    Ollama offline. Cannot run AI inference.
                                </div>
                            )}
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
};

export default SelectedFaultPanel;
