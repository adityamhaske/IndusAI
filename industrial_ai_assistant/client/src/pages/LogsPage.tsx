import React, { useState, useCallback, useEffect } from 'react';
import { Trash2, BarChart3, Database, ChevronDown, FolderOpen } from 'lucide-react';
import { Link } from 'react-router-dom';
import { faultApi } from '../services/faultApi';
import systemApi from '../services/systemApi';
import useAppStore from '../store/useAppStore';
import UploadZone from '../components/dashboard/UploadZone';
import FaultSummaryCard from '../components/dashboard/FaultSummaryCard';
import VirtualizedFaultTable from '../components/dashboard/VirtualizedFaultTable';
import SelectedFaultPanel from '../components/dashboard/SelectedFaultPanel';

import api from '../services/apiClient';

const LogsPage = () => {
    const activeProjectId = useAppStore(s => s.activeProjectId);
    const knowledgeStatus = useAppStore(s => s.knowledgeStatus);

    const [uploadInfo, setUploadInfo] = useState(null);
    const [summary, setSummary] = useState(null);
    const [selectedFault, setSelectedFault] = useState(null);
    const [faultDetail, setFaultDetail] = useState(null);
    const [analysis, setAnalysis] = useState(null);
    const [analysisError, setAnalysisError] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [uploadError, setUploadError] = useState(null);
    const [systemStatus, setSystemStatus] = useState(null);
    const [telemetryDatasets, setTelemetryDatasets] = useState([]);
    const [selectedDataset, setSelectedDataset] = useState('__upload__');
    const [loadingDataset, setLoadingDataset] = useState(false);

    // Fetch saved telemetry datasets for the active project
    const fetchTelemetry = useCallback(async () => {
        try {
            const pid = activeProjectId || 'default';
            const res = await api.get(`/api/projects/${pid}/telemetry`);
            const data = res.data;
            if (Array.isArray(data)) setTelemetryDatasets(data);
        } catch { /* silent */ }
    }, [activeProjectId]);

    useEffect(() => { fetchTelemetry(); }, [fetchTelemetry]);

    const handleDatasetSelect = useCallback(async (val) => {
        setSelectedDataset(val);
        if (val === '__upload__') return;
        setLoadingDataset(true);
        setUploadError(null);
        try {
            // Load existing dataset by its stored file_path
            const res = await api.post('/api/fault/load-dataset', { file_path: val });
            const result = res.data;
            setUploadInfo(result);
            const s = await faultApi.summary();
            setSummary(s);
        } catch (e: any) {
            setUploadError(e.response?.data?.detail || e.message || 'Failed to load dataset');
        } finally {
            setLoadingDataset(false);
        }
    }, []);

    // ── Upload ──────────────────────────────────────────────────────────────────
    const handleUpload = useCallback(async (file) => {
        setIsUploading(true);
        setUploadError(null);
        setSelectedFault(null);
        setFaultDetail(null);
        setAnalysis(null);
        try {
            const result = await faultApi.upload(file);
            setUploadInfo(result);
            // Immediately fetch summary
            const s = await faultApi.summary();
            setSummary(s);
        } catch (err) {
            setUploadError(err.response?.data?.message || err.message || 'Upload failed');
        } finally {
            setIsUploading(false);
        }
    }, []);

    // ── Row selection ───────────────────────────────────────────────────────────
    const handleRowSelect = useCallback(async (row) => {
        setSelectedFault(row);
        setAnalysis(null);
        try {
            const detail = await faultApi.detail(row.row_id);
            setFaultDetail(detail);
        } catch (e) {
            console.error('Detail fetch failed', e);
        }
    }, []);

    // ── Analysis ────────────────────────────────────────────────────────────────
    const handleAnalyze = useCallback(async (rowId, datasetHash, question = null) => {
        setIsAnalyzing(true);
        setAnalysisError(null);
        setAnalysis(null);
        try {
            const result = await faultApi.analyze(rowId, question);
            // Check if backend returned a structured error (HTTP 503 etc)
            if (result?.error_type) {
                setAnalysisError(result);
            } else {
                setAnalysis(result);
            }
        } catch (err) {
            const errData = err.response?.data;
            if (errData?.error_type) {
                setAnalysisError(errData);
            } else {
                setAnalysisError({
                    error_type: 'UNKNOWN_ERROR',
                    message: err.message || 'Analysis failed — check backend logs.',
                });
            }
        } finally {
            setIsAnalyzing(false);
        }
    }, []);

    // ── System health (poll every 30s) ─────────────────────────────────────────
    useEffect(() => {
        const fetch = async () => {
            try { setSystemStatus(await systemApi.health()); }
            catch { setSystemStatus(null); }
        };
        fetch();
        const t = setInterval(fetch, 30_000);
        return () => clearInterval(t);
    }, []);

    // ── Reset ───────────────────────────────────────────────────────────────────
    const handleReset = useCallback(async () => {
        await faultApi.reset();
        setUploadInfo(null);
        setSummary(null);
        setSelectedFault(null);
        setFaultDetail(null);
        setAnalysis(null);
    }, []);

    // ── Fetch page for table ───────────────────────────────────────────────────
    const fetchPage = useCallback((page, size) => faultApi.list(page, size), []);

    const isProjectLoaded = activeProjectId && activeProjectId !== 'default' && knowledgeStatus?.project_loaded;

    if (!isProjectLoaded) {
        return (
            <div className="flex flex-col h-full bg-industrial-50 items-center justify-center p-8 text-center animate-fade-in">
                <div className="w-20 h-20 bg-white border border-industrial-200 text-industrial-400 rounded-2xl shadow-sm flex items-center justify-center mb-6">
                    <Database className="w-10 h-10" />
                </div>
                <h2 className="text-2xl font-bold text-industrial-900 mb-3">Select a Project to Begin</h2>
                <p className="text-industrial-500 max-w-md mb-8 leading-relaxed">
                    To start analyzing PLC logic, P&IDs, and fault logs, you need to load an active project workspace.
                </p>
                <Link to="/project" className="bg-industrial-900 hover:bg-black text-white font-semibold py-3 px-6 rounded-xl transition-all shadow-sm flex items-center gap-2">
                    <FolderOpen className="w-4 h-4" /> Go to Projects
                </Link>
            </div>
        );
    }

    return (
        <div className="h-full overflow-y-auto bg-industrial-50">
            <div className="max-w-screen-2xl mx-auto p-6 space-y-6">

                {/* Upload Section */}
                <section className="bg-white border border-industrial-200 rounded-xl p-5 shadow-sm">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-base font-semibold text-industrial-800 flex items-center gap-2">
                            <BarChart3 className="w-5 h-5 text-primary-600" />
                            PLC Fault Log Upload
                        </h2>
                        {uploadInfo && (
                            <button
                                onClick={handleReset}
                                className="flex items-center gap-1.5 text-xs text-red-600 hover:text-red-800 border border-red-200 hover:bg-red-50 px-3 py-1.5 rounded-lg transition-colors"
                            >
                                <Trash2 className="w-3.5 h-3.5" />
                                Clear Dataset
                            </button>
                        )}
                    </div>
                    {/* Telemetry Source Selector */}
                    {telemetryDatasets.length > 0 && (
                        <div className="mb-4 flex items-center gap-3">
                            <Database className="w-4 h-4 text-industrial-400 flex-shrink-0" />
                            <span className="text-sm text-industrial-600 font-medium flex-shrink-0">Telemetry Source:</span>
                            <div className="relative flex-1 max-w-xs">
                                <select
                                    value={selectedDataset}
                                    onChange={e => handleDatasetSelect(e.target.value)}
                                    disabled={loadingDataset}
                                    className="w-full text-sm border border-industrial-200 rounded-lg px-3 py-1.5 text-industrial-700 bg-white focus:outline-none focus:border-primary-400 appearance-none pr-8 disabled:opacity-50"
                                >
                                    {telemetryDatasets.map(d => (
                                        <option key={d.id} value={d.file_path}>
                                            {d.file_name} {d.row_count > 0 ? `(${d.row_count.toLocaleString()} rows)` : ''}
                                        </option>
                                    ))}
                                    <option value="__upload__">📤 Upload New...</option>
                                </select>
                                <ChevronDown className="w-4 h-4 text-industrial-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
                            </div>
                            {loadingDataset && <span className="text-xs text-industrial-400 animate-pulse">Loading…</span>}
                        </div>
                    )}

                    {/* Show UploadZone only when 'Upload New' is selected or no saved datasets */}
                    {(selectedDataset === '__upload__' || telemetryDatasets.length === 0) && (
                        <div className="space-y-6">
                            <UploadZone onUpload={handleUpload} isLoading={isUploading} uploadInfo={uploadInfo} />
                            
                            {/* CSV Preview Table (Empty State Help) */}
                            {!uploadInfo && telemetryDatasets.length === 0 && (
                                <div className="mt-8 border border-industrial-200 rounded-xl overflow-hidden bg-white">
                                    <div className="bg-industrial-50 px-4 py-3 border-b border-industrial-200">
                                        <h3 className="text-sm font-semibold text-industrial-800">Expected CSV Format</h3>
                                        <p className="text-xs text-industrial-500 mt-1">Your log file must include exactly these 3 columns with the exact header names.</p>
                                    </div>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm text-left text-industrial-600">
                                            <thead className="text-xs text-industrial-700 uppercase bg-industrial-100/50 border-b border-industrial-200">
                                                <tr>
                                                    <th className="px-4 py-3 font-semibold">Timestamp</th>
                                                    <th className="px-4 py-3 font-semibold">FaultCode</th>
                                                    <th className="px-4 py-3 font-semibold">Description</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-industrial-100 font-mono text-xs">
                                                <tr className="hover:bg-industrial-50 transition-colors">
                                                    <td className="px-4 py-2 text-industrial-900">2026-05-24 10:23:45</td>
                                                    <td className="px-4 py-2 text-primary-600">F_1001</td>
                                                    <td className="px-4 py-2">Conveyor A Overload</td>
                                                </tr>
                                                <tr className="hover:bg-industrial-50 transition-colors">
                                                    <td className="px-4 py-2 text-industrial-900">2026-05-24 11:05:12</td>
                                                    <td className="px-4 py-2 text-primary-600">F_304B</td>
                                                    <td className="px-4 py-2">Pump 3 Low Pressure Warning</td>
                                                </tr>
                                                <tr className="hover:bg-industrial-50 transition-colors">
                                                    <td className="px-4 py-2 text-industrial-900">2026-05-24 13:40:00</td>
                                                    <td className="px-4 py-2 text-primary-600">E_STOP</td>
                                                    <td className="px-4 py-2">Emergency Stop Activated Zone 1</td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                    {uploadError && (
                        <div className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
                            {uploadError}
                        </div>
                    )}
                </section>

                {/* Summary */}
                {summary && (
                    <section>
                        <h2 className="text-sm font-semibold text-industrial-600 uppercase tracking-wide mb-3">
                            Fault Summary
                        </h2>
                        <FaultSummaryCard summary={summary} />
                    </section>
                )}

                {/* Table */}
                {uploadInfo && (
                    <section>
                        <h2 className="text-sm font-semibold text-industrial-600 uppercase tracking-wide mb-3">
                            Fault Log ({uploadInfo.total_rows?.toLocaleString()} rows)
                        </h2>
                        <VirtualizedFaultTable
                            totalRows={uploadInfo.total_rows}
                            fetchPage={fetchPage}
                            onRowSelect={handleRowSelect}
                            selectedRowId={selectedFault?.row_id}
                        />
                    </section>
                )}
            </div>

            {/* AI Analysis Drawer (Slide-in from right) */}
            {selectedFault && (
                <div className="fixed inset-0 z-50 flex justify-end overflow-hidden">
                    {/* Backdrop */}
                    <div
                        className="absolute inset-0 bg-industrial-900/20 backdrop-blur-sm transition-opacity"
                        onClick={() => setSelectedFault(null)}
                    ></div>

                    {/* Drawer Panel */}
                    <div className="relative w-full max-w-[500px] bg-white shadow-2xl h-full flex flex-col animate-slide-in-right border-l border-industrial-200">
                        <SelectedFaultPanel
                            fault={selectedFault}
                            detail={faultDetail}
                            analysis={analysis}
                            analysisError={analysisError}
                            systemStatus={systemStatus}
                            isAnalyzing={isAnalyzing}
                            onAnalyze={handleAnalyze}
                            datasetHash={uploadInfo?.dataset_hash}
                            onClose={() => setSelectedFault(null)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};

export default LogsPage;
