import React, { useState } from 'react';
import { AlertTriangle, CheckCircle, HelpCircle, ChevronDown, ChevronUp, FileText, Activity } from 'lucide-react';

const ConfidenceBadge = ({ score }) => {
    let color = 'bg-red-100 text-red-800 border-red-200';
    let icon = AlertTriangle;
    let label = 'Low Confidence';

    if (score >= 0.8) {
        color = 'bg-green-100 text-green-800 border-green-200';
        icon = CheckCircle;
        label = 'High Confidence';
    } else if (score >= 0.5) {
        color = 'bg-yellow-100 text-yellow-800 border-yellow-200';
        icon = HelpCircle;
        label = 'Medium Confidence';
    }

    const Icon = icon;

    return (
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${color}`}>
            <Icon className="w-3.5 h-3.5" />
            {label} ({Math.round(score * 100)}%)
        </span>
    );
};

const TagPill = ({ tag }) => (
    <span className="inline-flex items-center px-2 py-1 rounded bg-industrial-100 text-industrial-700 text-xs font-medium border border-industrial-200 hover:bg-industrial-200 cursor-pointer transition-colors">
        <Activity className="w-3 h-3 mr-1 text-industrial-500" />
        {tag}
    </span>
);

const SourceReference = ({ source }) => {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="border border-industrial-200 rounded-md bg-white overflow-hidden mb-2">
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center justify-between p-2 text-left bg-industrial-50 hover:bg-industrial-100 transition-colors"
            >
                <div className="flex items-center gap-2 text-sm font-medium text-industrial-700">
                    <FileText className="w-4 h-4 text-industrial-500" />
                    <span className="truncate">{source.file_name}</span>
                    <span className="text-xs text-industrial-400 font-normal">Page {source.page_label}</span>
                </div>
                {expanded ? <ChevronUp className="w-4 h-4 text-industrial-400" /> : <ChevronDown className="w-4 h-4 text-industrial-400" />}
            </button>

            {expanded && (
                <div className="p-3 text-xs text-industrial-600 border-t border-industrial-200 bg-white font-mono leading-relaxed">
                    {source.text}
                </div>
            )}
        </div>
    );
};

const StructuredResponseCard = ({ data }) => {
    // data expected to match ChatResponse schema
    // summary, causes (list), steps (list), tags (list), confidence_score, limitations, sources

    return (
        <div className="bg-white rounded-lg border border-industrial-200 shadow-sm overflow-hidden text-sm">
            {/* Header with Confidence */}
            <div className="bg-industrial-50 px-4 py-3 border-b border-industrial-200 flex items-center justify-between">
                <h3 className="font-semibold text-industrial-800">Analysis Result</h3>
                <ConfidenceBadge score={data.confidence_score} />
            </div>

            <div className="p-5 space-y-6">
                {/* Summary */}
                <section>
                    <h4 className="text-xs font-bold text-industrial-500 uppercase tracking-wider mb-2">Summary</h4>
                    <p className="text-industrial-800 leading-relaxed">{data.summary || data.answer}</p>
                </section>

                {/* Likely Causes */}
                {data.likely_causes && data.likely_causes.length > 0 && (
                    <section>
                        <h4 className="text-xs font-bold text-industrial-500 uppercase tracking-wider mb-2">Likely Causes</h4>
                        <ul className="list-disc pl-5 space-y-1 text-industrial-700">
                            {data.likely_causes.map((cause, idx) => (
                                <li key={idx}>{cause}</li>
                            ))}
                        </ul>
                    </section>
                )}

                {/* Resolution Steps */}
                {data.resolution_steps && data.resolution_steps.length > 0 && (
                    <section>
                        <h4 className="text-xs font-bold text-industrial-500 uppercase tracking-wider mb-2">Resolution Steps</h4>
                        <ol className="list-decimal pl-5 space-y-2 text-industrial-700">
                            {data.resolution_steps.map((step, idx) => (
                                <li key={idx} className="pl-1"><span className="font-medium text-industrial-900">{step.title}:</span> {step.description}</li>
                            ))}
                        </ol>
                    </section>
                )}

                {/* Related Tags */}
                {data.related_tags && data.related_tags.length > 0 && (
                    <section>
                        <h4 className="text-xs font-bold text-industrial-500 uppercase tracking-wider mb-2">Related PLC Tags</h4>
                        <div className="flex flex-wrap gap-2">
                            {data.related_tags.map((tag, idx) => (
                                <TagPill key={idx} tag={tag} />
                            ))}
                        </div>
                    </section>
                )}

                {/* Limitations/Warnings */}
                {data.limitations && (
                    <div className="bg-orange-50 border border-orange-100 rounded-md p-3 flex gap-3">
                        <AlertTriangle className="w-5 h-5 text-orange-500 flex-shrink-0" />
                        <div className="text-xs text-orange-800">
                            <span className="font-semibold block mb-1">Limitations</span>
                            {data.limitations}
                        </div>
                    </div>
                )}

                {/* Sources (Collapsible Section) */}
                {data.sources && data.sources.length > 0 && (
                    <section className="pt-4 border-t border-industrial-100">
                        <h4 className="text-xs font-bold text-industrial-500 uppercase tracking-wider mb-3">Source References</h4>
                        <div className="space-y-2">
                            {data.sources.map((src, idx) => (
                                <SourceReference key={idx} source={src} />
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </div>
    );
};

export default StructuredResponseCard;
