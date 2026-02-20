import React, { useState } from 'react';
import {
    ChevronDown, ChevronRight, AlertTriangle, CheckCircle2,
    Lightbulb, Wrench, BookOpen, ShieldAlert, Database, Zap
} from 'lucide-react';

// ── Helpers ────────────────────────────────────────────────────────────────────
function ConfidenceBadge({ level }) {
    const map = {
        HIGH: 'bg-green-100 text-green-700 border-green-200',
        MEDIUM: 'bg-yellow-100 text-yellow-700 border-yellow-200',
        LOW: 'bg-red-100 text-red-600 border-red-200',
    };
    return (
        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${map[level] || map.LOW}`}>
            {level}
        </span>
    );
}

function KnowledgeModeBadge({ mode }) {
    const isProject = mode === 'PROJECT';
    return (
        <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border ${isProject ? 'bg-green-50 text-green-700 border-green-200' : 'bg-yellow-50 text-yellow-700 border-yellow-200'
            }`}>
            {isProject ? '🟢 Project' : '🟡 General'}
        </span>
    );
}

function Section({ icon: Icon, color, title, children }) {
    return (
        <div className="space-y-1.5">
            <div className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide ${color}`}>
                <Icon className="w-3.5 h-3.5" />
                {title}
            </div>
            {children}
        </div>
    );
}

function BulletList({ items, ordered = false, dim = false }) {
    if (!items?.length) return null;
    const Tag = ordered ? 'ol' : 'ul';
    return (
        <Tag className={`space-y-1 ${ordered ? 'list-decimal pl-4' : 'list-disc pl-4'}`}>
            {items.map((item, i) => (
                <li key={i} className={`text-sm leading-relaxed ${dim ? 'text-industrial-400' : 'text-industrial-700'}`}>
                    {item}
                </li>
            ))}
        </Tag>
    );
}

function Collapsible({ title, children }) {
    const [open, setOpen] = useState(false);
    return (
        <div>
            <button
                onClick={() => setOpen(v => !v)}
                className="flex items-center gap-1.5 text-xs text-industrial-400 hover:text-industrial-600 transition-colors"
            >
                {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                {title}
            </button>
            {open && <div className="mt-2">{children}</div>}
        </div>
    );
}

// ── Main AnswerCard ────────────────────────────────────────────────────────────
/**
 * Renders a structured LLM answer from KnowledgeQueryResponse.
 *
 * Expected shape of `data`:
 *   summary, root_causes[], recommended_actions[], supporting_evidence[],
 *   limitations[], confidence, knowledge_mode, prompt_version,
 *   structured_hits[], documentation_sources[], hallucinated_tags_removed[],
 *   warnings[]
 */
const AnswerCard = ({ data }) => {
    // Parse summary — may itself be a JSON string from older responses
    let summary = data.summary || '';
    let rootCauses = data.root_causes || [];
    let recommendedActions = data.recommended_actions || [];
    let supportingEvidence = data.supporting_evidence || [];
    let limitations = data.limitations || [];
    let confidence = data.confidence || 'LOW';

    // Backward-compat: if summary looks like JSON (old format), parse it
    if (summary.trim().startsWith('{')) {
        try {
            const parsed = JSON.parse(summary);
            rootCauses = parsed.root_causes || parsed.likely_causes || rootCauses;
            recommendedActions = parsed.recommended_actions || parsed.resolution_steps || recommendedActions;
            supportingEvidence = parsed.supporting_evidence || parsed.source_sections || supportingEvidence;
            limitations = parsed.limitations || [parsed.limitations] || limitations;
            confidence = parsed.confidence || confidence;
            summary = parsed.summary || parsed.answer || summary;
        } catch { /* leave as-is */ }
    }

    // Merge structured hits and documentation sources into evidence
    const structuredEvidence = (data.structured_hits || []).map(h =>
        `[${h.hit_type?.toUpperCase()}] ${h.data?.name || h.data?.slot || JSON.stringify(h.data).slice(0, 60)}`
    );
    const docSources = (data.documentation_sources || []).map(src =>
        `📄 ${src.split('/').pop()}`
    );
    const allEvidence = [...supportingEvidence, ...structuredEvidence, ...docSources].filter(Boolean);

    return (
        <div className="space-y-4">
            {/* ── Summary ─────────────────────────────────────────────────── */}
            <Section icon={Lightbulb} color="text-primary-600" title="Summary">
                <p className="text-sm text-industrial-800 leading-relaxed font-medium">{summary}</p>
            </Section>

            {/* ── Root Causes ─────────────────────────────────────────────── */}
            {rootCauses.length > 0 && (
                <Section icon={AlertTriangle} color="text-orange-600" title="Root Causes">
                    <BulletList items={rootCauses} />
                </Section>
            )}

            {/* ── Recommended Actions ─────────────────────────────────────── */}
            {recommendedActions.length > 0 && (
                <Section icon={Wrench} color="text-blue-600" title="Recommended Actions">
                    <BulletList items={recommendedActions} ordered />
                </Section>
            )}

            {/* ── Supporting Evidence (collapsible) ───────────────────────── */}
            {allEvidence.length > 0 && (
                <Section icon={BookOpen} color="text-industrial-400" title="Supporting Evidence">
                    <Collapsible title={`${allEvidence.length} source${allEvidence.length > 1 ? 's' : ''}`}>
                        <BulletList items={allEvidence} dim />
                    </Collapsible>
                </Section>
            )}

            {/* ── Limitations ─────────────────────────────────────────────── */}
            {limitations.length > 0 && (
                <Section icon={ShieldAlert} color="text-industrial-400" title="Limitations">
                    <BulletList items={limitations} dim />
                </Section>
            )}

            {/* ── Hallucination warning ────────────────────────────────────── */}
            {data.hallucinated_tags_removed?.length > 0 && (
                <div className="flex items-start gap-2 text-xs text-orange-700 bg-orange-50 border border-orange-200 rounded-lg p-2">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                    <span><strong>{data.hallucinated_tags_removed.length} invented tag(s) removed:</strong> {data.hallucinated_tags_removed.join(', ')}</span>
                </div>
            )}

            {/* ── System warnings ─────────────────────────────────────────── */}
            {data.warnings?.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-lg p-2">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                    {w}
                </div>
            ))}

            {/* ── Footer: mode + confidence + version ─────────────────────── */}
            <div className="flex items-center gap-2 pt-1 border-t border-industrial-100 flex-wrap">
                <KnowledgeModeBadge mode={data.knowledge_mode} />
                <ConfidenceBadge level={confidence} />
                <span className="text-[10px] text-industrial-300 font-mono ml-auto">
                    {data.prompt_version}
                    {data.total_latency_ms > 0 && ` · ${data.total_latency_ms.toFixed(0)}ms`}
                </span>
            </div>
        </div>
    );
};

export default AnswerCard;
