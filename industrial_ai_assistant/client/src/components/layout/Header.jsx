import React, { useEffect, useState, useCallback } from 'react';
import { Bell, Cpu, Wifi, WifiOff, AlertCircle, CheckCircle2, RefreshCw } from 'lucide-react';
import systemApi from '../../api/systemApi';

// ── Status badge colours ──────────────────────────────────────────────────────
const STATUS_CONFIG = {
    loading: {
        dot: 'bg-industrial-400 animate-pulse',
        text: 'Checking...',
        icon: <RefreshCw className="w-3 h-3 animate-spin" />,
        cls: 'text-industrial-500',
    },
    healthy: {
        dot: 'bg-green-500',
        text: 'All Systems Healthy',
        icon: <CheckCircle2 className="w-3 h-3" />,
        cls: 'text-green-700',
    },
    llm_down: {
        dot: 'bg-red-500 animate-pulse',
        text: 'LLM Not Connected',
        icon: <WifiOff className="w-3 h-3" />,
        cls: 'text-red-600',
    },
    rag_down: {
        dot: 'bg-yellow-500 animate-pulse',
        text: 'RAG Not Initialized',
        icon: <AlertCircle className="w-3 h-3" />,
        cls: 'text-yellow-700',
    },
    degraded: {
        dot: 'bg-orange-500 animate-pulse',
        text: 'System Degraded',
        icon: <AlertCircle className="w-3 h-3" />,
        cls: 'text-orange-600',
    },
    error: {
        dot: 'bg-red-500',
        text: 'Cannot Reach Backend',
        icon: <WifiOff className="w-3 h-3" />,
        cls: 'text-red-700',
    },
};

function resolveStatusKey(health) {
    if (!health) return 'error';
    if (health.status === 'healthy') return 'healthy';
    if (!health.llm_connected) return 'llm_down';
    if (!health.rag_connected) return 'rag_down';
    return 'degraded';
}

// ── Tooltip panel ─────────────────────────────────────────────────────────────
const HealthTooltip = ({ health }) => {
    if (!health) return null;
    const rows = [
        { label: 'LLM', ok: health.llm_connected, detail: health.llm_reason || health.llm_url },
        { label: 'RAG', ok: health.rag_connected, detail: health.rag_reason || '—' },
        { label: 'Vector DB', ok: health.vector_store_connected, detail: health.vector_store_reason || health.vector_store_type },
    ];
    return (
        <div className="absolute right-0 top-full mt-2 w-72 bg-white border border-industrial-200 rounded-xl shadow-xl z-50 p-3 text-xs">
            <div className="font-semibold text-industrial-700 mb-2 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5" /> System Health
            </div>
            {rows.map(r => (
                <div key={r.label} className="flex items-start gap-2 py-1.5 border-b border-industrial-100 last:border-0">
                    <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${r.ok ? 'bg-green-500' : 'bg-red-500'}`} />
                    <div>
                        <span className="font-medium text-industrial-700">{r.label}</span>
                        {r.detail && (
                            <p className="text-industrial-400 mt-0.5 break-all">{r.detail}</p>
                        )}
                    </div>
                </div>
            ))}
            <p className="text-industrial-300 mt-2">Polls every 30 s</p>
        </div>
    );
};

// ── Main Header ───────────────────────────────────────────────────────────────
const Header = ({ title }) => {
    const [statusKey, setStatusKey] = useState('loading');
    const [health, setHealth] = useState(null);
    const [showTooltip, setShowTooltip] = useState(false);

    const fetchHealth = useCallback(async () => {
        try {
            const data = await systemApi.health();
            setHealth(data);
            setStatusKey(resolveStatusKey(data));
        } catch {
            setHealth(null);
            setStatusKey('error');
        }
    }, []);

    useEffect(() => {
        fetchHealth();
        const interval = setInterval(fetchHealth, 30_000);
        return () => clearInterval(interval);
    }, [fetchHealth]);

    const cfg = STATUS_CONFIG[statusKey] || STATUS_CONFIG.loading;

    return (
        <header className="h-16 bg-white border-b border-industrial-200 flex items-center justify-between px-6 shadow-sm z-10">
            {/* Left */}
            <div className="flex items-center gap-4">
                <h1 className="text-xl font-semibold text-industrial-800">{title}</h1>
                <div className="h-4 w-px bg-industrial-300 mx-2 hidden md:block" />

                {/* Dynamic status badge */}
                <div
                    className="hidden md:flex items-center gap-1.5 text-xs cursor-pointer relative select-none"
                    onClick={() => setShowTooltip(v => !v)}
                    onBlur={() => setShowTooltip(false)}
                    tabIndex={0}
                >
                    <span className={`flex items-center gap-1.5 ${cfg.cls}`}>
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
                        {cfg.icon}
                        {cfg.text}
                    </span>
                    {showTooltip && <HealthTooltip health={health} />}
                </div>
            </div>

            {/* Right */}
            <div className="flex items-center gap-3">
                {/* Confidence legend */}
                <div className="hidden md:flex items-center gap-3 mr-4 text-xs bg-industrial-50 px-3 py-1.5 rounded-full border border-industrial-100">
                    <span className="flex items-center gap-1 text-industrial-600">
                        <span className="w-2 h-2 rounded-full bg-green-500" /> High
                    </span>
                    <span className="flex items-center gap-1 text-industrial-600">
                        <span className="w-2 h-2 rounded-full bg-yellow-500" /> Med
                    </span>
                </div>

                <button
                    onClick={fetchHealth}
                    title="Refresh health status"
                    className="p-2 text-industrial-400 hover:text-industrial-600 hover:bg-industrial-100 rounded-full transition-colors"
                >
                    <RefreshCw className="w-4 h-4" />
                </button>

                <button className="p-2 text-industrial-400 hover:text-industrial-600 hover:bg-industrial-100 rounded-full transition-colors relative">
                    <Bell className="w-5 h-5" />
                    <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white" />
                </button>

                <div className="h-8 w-px bg-industrial-200 mx-2" />

                <button className="flex items-center gap-2 text-sm font-medium text-industrial-700 hover:text-industrial-900 transition-colors">
                    <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center font-bold">
                        JD
                    </div>
                    <span className="hidden sm:block">John Doe</span>
                </button>
            </div>
        </header>
    );
};

export default Header;
