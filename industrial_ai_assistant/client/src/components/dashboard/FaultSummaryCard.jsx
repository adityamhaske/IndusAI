import React from 'react';
import { Activity, AlertTriangle, Clock, Hash, Zap } from 'lucide-react';

const Card = ({ icon: Icon, label, value, sub, accent }) => (
    <div className={`bg-white rounded-lg border p-4 flex items-start gap-3 ${accent || 'border-industrial-200'}`}>
        <div className={`p-2 rounded-lg ${accent ? 'bg-red-50' : 'bg-industrial-50'}`}>
            <Icon className={`w-5 h-5 ${accent ? 'text-red-600' : 'text-industrial-600'}`} />
        </div>
        <div className="min-w-0">
            <div className="text-xs text-industrial-500 font-medium">{label}</div>
            <div className="text-xl font-bold text-industrial-900 truncate">{value}</div>
            {sub && <div className="text-xs text-industrial-400 truncate">{sub}</div>}
        </div>
    </div>
);

const FaultSummaryCard = ({ summary }) => {
    if (!summary) return null;

    const start = summary.time_range_start
        ? new Date(summary.time_range_start).toLocaleDateString()
        : '—';
    const end = summary.time_range_end
        ? new Date(summary.time_range_end).toLocaleDateString()
        : '—';

    return (
        <div className="space-y-3">
            {summary.burst_detected && (
                <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5 text-sm text-red-800">
                    <Zap className="w-4 h-4 text-red-600" />
                    <strong>Burst Detected:</strong>&nbsp;{summary.max_burst_window_description}
                </div>
            )}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Card icon={Activity} label="Total Faults" value={summary.total_rows?.toLocaleString()} />
                <Card icon={Hash} label="Unique Codes" value={summary.unique_fault_codes} />
                <Card
                    icon={AlertTriangle}
                    label="Most Common"
                    value={summary.most_common_fault}
                    sub={`${summary.most_common_count?.toLocaleString()} occurrences`}
                    accent={summary.burst_detected ? 'border-red-200' : undefined}
                />
                <Card icon={Clock} label="Time Range" value={start} sub={`→ ${end}`} />
            </div>
        </div>
    );
};

export default FaultSummaryCard;
