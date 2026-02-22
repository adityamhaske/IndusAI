import React, { useState } from 'react';
import {
    Cpu, Clock, Activity, Loader2, ChevronDown, ChevronUp,
    MessageSquare, AlertTriangle, X, PlayCircle
} from 'lucide-react';

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
        <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-industrial-200 border border-industrial-200 rounded-lg overflow-hidden font-mono text-xs">
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
                    {evidence?.burst_detected ? `YES (${evidence.burst_count}/${evidence.burst_window_minutes}m)` : 'NO'}
                </span>
            </div>
            <div className="bg-industrial-50 p-2 flex flex-col justify-center">
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">Co-Occurrence</span>
                <span className="font-semibold text-industrial-800 truncate">
                    {evidence?.co_occurrence?.[0] ? `${evidence.co_occurrence[0].fault} (x${evidence.co_occurrence[0].count})` : 'NONE'}
                </span>
            </div>
            <div className="bg-industrial-50 p-2 flex flex-col justify-center">
                <span className="text-industrial-400 text-[10px] uppercase tracking-wider mb-0.5">Trend</span>
                <TrendIndicator trend={evidence?.trend} />
            </div>
        </div>
    );
};

const SelectedFaultPanel = ({ fault, detail, analysis, analysisError, systemStatus, isAnalyzing, onAnalyze, datasetHash, onClose }) => {
    const [question, setQuestion] = useState('');
    const [showEvidence, setShowEvidence] = useState(false);

    const llmDown = systemStatus !== null && systemStatus !== undefined && !systemStatus.llm_connected;

    if (!fault) return null;

    const handleAnalyze = async () => {
        await onAnalyze(fault.row_id, datasetHash, question.trim() || null);
    };

    const isAnalyzed = !!analysis;
    const isIntegrityFailure = analysis?.statistics?.integrity_passed === false;
    const isParseFailed = analysis?.diagnosis?.startsWith('[STRUCTURED PARSE FAILED - RAW OUTPUT]');
    const displayDiagnosis = isParseFailed ? analysis.diagnosis.replace('[STRUCTURED PARSE FAILED - RAW OUTPUT]\n', '') : analysis?.diagnosis;

    return (
        <div className="bg-white flex flex-col h-full w-[380px] shadow-2xl absolute right-0 top-0 bottom-0 z-50">
            {/* Header */}
            <div className="bg-industrial-900 text-white px-4 py-3 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-industrial-400" />
                    <span className="text-sm font-semibold tracking-wide">DIAGNOSTIC INSTRUMENT</span>
                </div>
                <button
                    onClick={onClose}
                    className="p-1 text-industrial-400 hover:text-white hover:bg-industrial-700 rounded transition-colors"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 pb-8">

                {/* STATE 1: Not Analyzed Yet */}
                {!isAnalyzed && !isAnalyzing && (
                    <div className="space-y-6">
                        <div className="space-y-4">
                            <div>
                                <h3 className="text-xs font-semibold text-industrial-500 uppercase tracking-wider mb-1">Target</h3>
                                <div className="text-xl font-bold font-mono text-industrial-900">{fault.fault_code}</div>
                                <div className="text-sm text-industrial-600 mt-1">{fault.message}</div>
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

                        {/* Optional Question Input */}
                        <div className="space-y-2">
                            <label className="text-xs font-semibold text-industrial-600 uppercase tracking-wider">
                                Custom Directive (Optional)
                            </label>
                            <textarea
                                value={question}
                                onChange={e => setQuestion(e.target.value)}
                                placeholder="E.g., Why did this happen during cycle reset?"
                                rows={2}
                                className="w-full text-sm border border-industrial-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-industrial-500 resize-none bg-industrial-50 text-industrial-900"
                            />
                        </div>

                        <button
                            onClick={handleAnalyze}
                            disabled={llmDown}
                            className="w-full flex items-center justify-center gap-2 bg-industrial-900 hover:bg-black disabled:bg-industrial-300 text-white py-3 rounded-lg text-sm font-semibold transition-colors"
                        >
                            <Activity className="w-4 h-4" />
                            {question ? 'PROCESS DIRECTIVE' : 'RUN DIAGNOSTIC'}
                        </button>

                        {llmDown && (
                            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-md p-3">
                                <strong>System Offline:</strong> LLM connection failed. Start Ollama to proceed.
                            </div>
                        )}
                        {analysisError && (
                            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-md p-3">
                                <strong>Error:</strong> {analysisError.message || 'Analysis failed'}
                            </div>
                        )}
                    </div>
                )}

                {/* STATE 2: Loading Analysis */}
                {isAnalyzing && (
                    <div className="flex flex-col items-center justify-center h-[60vh] text-industrial-400 space-y-4">
                        <Loader2 className="w-8 h-8 animate-spin text-industrial-600" />
                        <div className="text-sm font-medium animate-pulse">Computing integrity & models...</div>
                    </div>
                )}

                {/* STATE 3: Analysis Complete */}
                {isAnalyzed && !isAnalyzing && (
                    <div className="space-y-6 animate-fade-in">

                        {/* 1. Stat Strip */}
                        <StatStrip fault={fault} evidence={analysis.evidence} confidence={analysis.confidence} />

                        {/* 1.5 INTEGRITY FAILURE OVERRIDE */}
                        {isIntegrityFailure ? (
                            <div className="bg-red-50 border border-red-200 p-4 rounded-lg">
                                <h3 className="text-xs font-bold text-red-700 uppercase tracking-widest flex items-center gap-1.5 mb-2">
                                    <AlertTriangle className="w-4 h-4" /> DATA INTEGRITY WARNING
                                </h3>
                                <p className="text-sm text-red-900 leading-snug">
                                    The statistical engine detected contradictions in the event log (e.g., Burst recorded without sufficient hourly volume).
                                    <strong> AI Inference was suppressed to prevent hallucinations.</strong>
                                </p>
                            </div>
                        ) : (
                            <>
                                {/* 2. Diagnosis (Primary) */}
                                <div className="space-y-2">
                                    <h3 className="text-[10px] font-bold text-industrial-400 uppercase tracking-widest flex justify-between">
                                        <span>Diagnosis</span>
                                        <div className="flex gap-2">
                                            {isParseFailed && (
                                                <span className="px-1.5 rounded bg-amber-100 text-amber-700 font-bold border border-amber-200">
                                                    RAW OUTPUT (PARSE FAILED)
                                                </span>
                                            )}
                                            <span className={`px-1.5 rounded ${analysis.confidence === 'HIGH' ? 'bg-green-100 text-green-700' :
                                                analysis.confidence === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'
                                                }`}>
                                                CONFIDENCE: {analysis.confidence}
                                            </span>
                                        </div>
                                    </h3>
                                    {isParseFailed ? (
                                        <div className="bg-amber-50 rounded p-3 border border-amber-200 text-amber-900 text-sm font-mono whitespace-pre-wrap">
                                            {displayDiagnosis}
                                        </div>
                                    ) : (
                                        <p className="text-lg font-bold text-industrial-900 leading-snug">
                                            {displayDiagnosis}
                                        </p>
                                    )}
                                </div>
                            </>
                        )}


                        {/* 3. Evidence / Deterministic Stats (Collapsible) */}
                        <div className="border border-industrial-200 rounded-lg overflow-hidden bg-white">
                            <button
                                onClick={() => setShowEvidence(!showEvidence)}
                                className="w-full flex items-center justify-between px-3 py-2.5 bg-industrial-50 hover:bg-industrial-100 text-xs font-semibold text-industrial-700 transition-colors"
                            >
                                <div className="flex items-center gap-2 uppercase tracking-wide">
                                    <Activity className="w-3.5 h-3.5 text-industrial-500" />
                                    Raw Telemetry Data
                                </div>
                                {showEvidence ? <ChevronUp className="w-4 h-4 text-industrial-400" /> : <ChevronDown className="w-4 h-4 text-industrial-400" />}
                            </button>

                            {showEvidence && analysis.statistics && (
                                <div className="px-4 py-3 bg-white border-t border-industrial-100">
                                    <ul className="space-y-2 text-sm text-industrial-700">
                                        <li className="flex justify-between items-center py-1 border-b border-industrial-50">
                                            <span className="text-industrial-500">Anomaly Target Score</span>
                                            <span className="font-mono font-medium">{analysis.statistics.anomaly_score?.toFixed(2)}x</span>
                                        </li>
                                        <li className="flex justify-between items-center py-1 border-b border-industrial-50">
                                            <span className="text-industrial-500">Rolling Avg (1H)</span>
                                            <span className="font-mono font-medium">{analysis.statistics.rolling_avg_1h?.toFixed(1)}/hr</span>
                                        </li>
                                        <li className="flex justify-between items-center py-1 border-b border-industrial-50">
                                            <span className="text-industrial-500">Vol ∆ (30m)</span>
                                            <span className="font-mono font-medium">{analysis.statistics.delta_last_30m > 0 ? '+' : ''}{analysis.statistics.delta_last_30m?.toFixed(0)}</span>
                                        </li>
                                        <li className="flex justify-between items-center py-1 border-b border-industrial-50">
                                            <span className="text-industrial-500">Data Integrity Passed</span>
                                            <span className={`font-mono font-medium ${analysis.statistics.integrity_passed ? 'text-green-600' : 'text-red-600'}`}>
                                                {analysis.statistics.integrity_passed ? 'TRUE' : 'FALSE'}
                                            </span>
                                        </li>
                                    </ul>
                                </div>
                            )}
                        </div>

                        {/* 4. Recommended Action */}
                        <div className="bg-industrial-900 text-white rounded-lg p-4 shadow-sm border border-industrial-800">
                            <h3 className="text-[10px] font-bold text-industrial-400 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                                <PlayCircle className="w-3 h-3 text-primary-400" /> Immediate Instruction
                            </h3>
                            <p className="text-sm font-medium leading-relaxed">
                                {analysis.primary_action}
                            </p>
                        </div>

                        {/* Footer Re-analyze or close info */}
                        <div className="pt-4 flex justify-end">
                            <span className="text-[10px] text-industrial-400 font-mono tracking-wider">
                                SYS_{analysis.analysis_version} • {analysis.total_latency_ms?.toFixed(0)}MS
                            </span>
                        </div>

                    </div>
                )}
            </div>
        </div>
    );
};

export default SelectedFaultPanel;
