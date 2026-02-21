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
const AnswerCard = ({ data }) => {
    const intentType = data.intent_type || 'GENERAL_QUERY';

    // Parse the inner Pydantic JSON string
    let parsed = {};
    if (typeof data.answer === 'string' && data.answer.trim().startsWith('{')) {
        try {
            parsed = JSON.parse(data.answer);
        } catch {
            parsed = { explanation: data.answer }; // Fallback
        }
    } else {
        // Just in case it's already an object
        parsed = typeof data.answer === 'object' ? data.answer : { explanation: String(data.answer || '') };
    }

    // Merge structured hits and documentation sources into evidence for all schemas
    const structuredEvidence = (data.structured_hits || []).map(h =>
        `[${h.hit_type?.toUpperCase()}] ${h.data?.name || h.data?.slot || JSON.stringify(h.data).slice(0, 60)}`
    );
    const docSources = (data.semantic_sources || data.documentation_sources || []).map(src =>
        `📄 ${src.split('/').pop()}`
    );

    // Render specific layout inside a wrapper
    const renderContent = () => {
        if (intentType === 'FAULT_ANALYSIS') {
            const rootCauses = parsed.root_causes || [];
            const recActions = parsed.recommended_actions || [];
            const limitations = parsed.limitations || [];
            const allEvidence = [...(parsed.supporting_evidence || []), ...structuredEvidence, ...docSources].filter(Boolean);

            return (
                <div className="space-y-4">
                    <Section icon={Lightbulb} color="text-primary-600" title="Summary">
                        <p className="text-sm text-industrial-800 leading-relaxed font-medium">{parsed.summary}</p>
                    </Section>
                    {rootCauses.length > 0 && (
                        <Section icon={AlertTriangle} color="text-orange-600" title="Root Causes">
                            <BulletList items={rootCauses} />
                        </Section>
                    )}
                    {recActions.length > 0 && (
                        <Section icon={Wrench} color="text-blue-600" title="Recommended Actions">
                            <BulletList items={recActions} ordered />
                        </Section>
                    )}
                    {allEvidence.length > 0 && (
                        <Section icon={BookOpen} color="text-industrial-400" title="Supporting Evidence">
                            <Collapsible title={`${allEvidence.length} source${allEvidence.length > 1 ? 's' : ''}`}>
                                <BulletList items={allEvidence} dim />
                            </Collapsible>
                        </Section>
                    )}
                    {limitations.length > 0 && (
                        <Section icon={ShieldAlert} color="text-industrial-400" title="Limitations">
                            <BulletList items={limitations} dim />
                        </Section>
                    )}
                </div>
            );
        }

        if (intentType === 'FILE_EXPLANATION') {
            const structure = parsed.structure_breakdown || [];
            const fields = parsed.key_fields_explained || [];
            const examples = parsed.examples || [];
            return (
                <div className="space-y-4">
                    <Section icon={Lightbulb} color="text-primary-600" title="Summary">
                        <p className="text-sm text-industrial-800 leading-relaxed font-medium">{parsed.summary}</p>
                    </Section>
                    {structure.length > 0 && (
                        <Section icon={Database} color="text-blue-600" title="Structure Breakdown">
                            <BulletList items={structure} />
                        </Section>
                    )}
                    {parsed.engineering_insight && (
                        <Section icon={Wrench} color="text-purple-600" title="Engineering Insight">
                            <p className="text-sm text-industrial-700 leading-relaxed">{parsed.engineering_insight}</p>
                        </Section>
                    )}
                    {fields.length > 0 && (
                        <Section icon={BookOpen} color="text-industrial-600" title="Key Fields">
                            <BulletList items={fields} />
                        </Section>
                    )}
                    {examples.length > 0 && (
                        <Section icon={Zap} color="text-green-600" title="Examples">
                            <BulletList items={examples} />
                        </Section>
                    )}
                </div>
            );
        }

        // GENERAL_QUERY or SYSTEM_FLOW fallback
        const allSources = [...(parsed.supporting_sources || []), ...structuredEvidence, ...docSources].filter(Boolean);
        return (
            <div className="space-y-4">
                <Section icon={Lightbulb} color="text-primary-600" title="Explanation">
                    <p className="text-sm text-industrial-800 leading-relaxed font-medium whitespace-pre-wrap">{parsed.explanation}</p>
                </Section>
                {allSources.length > 0 && (
                    <Section icon={BookOpen} color="text-industrial-400" title="Sources">
                        <Collapsible title={`${allSources.length} source${allSources.length > 1 ? 's' : ''}`}>
                            <BulletList items={allSources} dim />
                        </Collapsible>
                    </Section>
                )}
            </div>
        );
    };

    return (
        <div className="space-y-4">
            {renderContent()}

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
                {intentType === 'FAULT_ANALYSIS' && <KnowledgeModeBadge mode={data.knowledge_mode} />}
                <ConfidenceBadge level={data.confidence || parsed.confidence || 'LOW'} />
                <span className="text-[10px] text-industrial-300 font-mono ml-auto">
                    {data.prompt_version}
                    {data.total_latency_ms > 0 && ` · ${data.total_latency_ms.toFixed(0)}ms`}
                </span>
            </div>
        </div>
    );
};

export default AnswerCard;
