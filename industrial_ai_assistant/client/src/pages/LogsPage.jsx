import React, { useState, useCallback, useEffect } from 'react';
import { Trash2, BarChart3, RefreshCw } from 'lucide-react';
import { faultApi } from '../services/faultApi';
import systemApi from '../services/systemApi';
import UploadZone from '../components/dashboard/UploadZone';
import FaultSummaryCard from '../components/dashboard/FaultSummaryCard';
import VirtualizedFaultTable from '../components/dashboard/VirtualizedFaultTable';
import SelectedFaultPanel from '../components/dashboard/SelectedFaultPanel';

const LogsPage = () => {
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

    return (
        <div className="h-full overflow-y-auto">
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
                    <UploadZone onUpload={handleUpload} isLoading={isUploading} uploadInfo={uploadInfo} />
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
                    <div className="relative w-full max-w-[360px] bg-white shadow-2xl h-full flex flex-col animate-slide-in-right border-l border-industrial-200">
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
