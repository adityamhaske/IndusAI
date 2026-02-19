import React, { useCallback, useState } from 'react';
import { UploadCloud, X, AlertCircle, CheckCircle } from 'lucide-react';

const UploadZone = ({ onUpload, isLoading, uploadInfo }) => {
    const [dragOver, setDragOver] = useState(false);
    const [error, setError] = useState(null);

    const handleFile = useCallback(async (file) => {
        if (!file) return;
        if (!file.name.endsWith('.csv')) {
            setError('Only CSV files are supported.');
            return;
        }
        setError(null);
        await onUpload(file);
    }, [onUpload]);

    const onDrop = useCallback((e) => {
        e.preventDefault();
        setDragOver(false);
        handleFile(e.dataTransfer.files[0]);
    }, [handleFile]);

    const onInputChange = (e) => handleFile(e.target.files[0]);

    return (
        <div className="space-y-4">
            <label
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                className={`flex flex-col items-center justify-center w-full h-44 border-2 border-dashed rounded-xl cursor-pointer transition-all
          ${dragOver ? 'border-primary-500 bg-primary-50' : 'border-industrial-300 bg-white hover:border-primary-400 hover:bg-industrial-50'}
          ${isLoading ? 'opacity-50 pointer-events-none' : ''}`}
            >
                <input type="file" accept=".csv" className="hidden" onChange={onInputChange} disabled={isLoading} />
                <UploadCloud className={`w-12 h-12 mb-2 ${dragOver ? 'text-primary-500' : 'text-industrial-400'}`} />
                <p className="text-sm font-medium text-industrial-700">
                    {isLoading ? 'Uploading & parsing…' : 'Drop fault CSV here or click to browse'}
                </p>
                <p className="text-xs text-industrial-400 mt-1">Max 50 MB · 250,000 rows</p>
            </label>

            {error && (
                <div className="flex items-center gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    {error}
                </div>
            )}

            {uploadInfo && !isLoading && (
                <div className="flex items-start gap-3 text-sm bg-green-50 border border-green-200 rounded-lg p-3">
                    <CheckCircle className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                        <div className="font-medium text-green-800">{uploadInfo.source_filename}</div>
                        <div className="text-green-700 mt-0.5">
                            {uploadInfo.total_rows.toLocaleString()} rows loaded
                            {uploadInfo.sampled && <span className="text-orange-600"> (sampled to 200k)</span>}
                            &nbsp;· parse: {uploadInfo.parse_duration_ms}ms
                            · stats: {uploadInfo.stats_duration_ms}ms
                        </div>
                        {uploadInfo.warnings?.length > 0 && (
                            <ul className="text-xs text-orange-600 mt-1 space-y-0.5">
                                {uploadInfo.warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}
                            </ul>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default UploadZone;
