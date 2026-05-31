/**
 * LandingPage.tsx — Public marketing page for ControlsAI.
 * Shows to all visitors before login.
 */
import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Cpu, ArrowRight, CheckCircle, Layers, Lock, Server } from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────
interface FeatureCard {
    icon: React.ReactNode;
    tag: string;
    title: string;
    description: string;
}

// ── Feature Card Component ─────────────────────────────────────────────────────
const Card = ({ card }: { card: FeatureCard }) => (
    <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6 flex flex-col gap-4 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200">
        <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-[#EEF2FF] text-[#3B5BDB] flex items-center justify-center flex-shrink-0">
                {card.icon}
            </div>
            <div>
                <span className="text-[10px] font-bold tracking-widest text-[#3B5BDB] uppercase">{card.tag}</span>
                <h3 className="text-sm font-bold text-[#0F172A] mt-0.5">{card.title}</h3>
            </div>
        </div>
        <p className="text-[13px] text-[#64748B] leading-relaxed">{card.description}</p>
    </div>
);

// ── Landing Page ───────────────────────────────────────────────────────────────
export default function LandingPage() {
    const navigate = useNavigate();

    const features: FeatureCard[] = [
        {
            icon: <CheckCircle className="w-5 h-5" />,
            tag: 'Verified',
            title: 'Hallucination-free answers',
            description:
                'Every response is checked against canonical equipment tags and source documents before it reaches the technician.',
        },
        {
            icon: <Layers className="w-5 h-5" />,
            tag: 'Hybrid Search',
            title: 'Precise part identification',
            description:
                'Dense + BM25/RRF retrieval prevents conflating similar part numbers like E-404 vs E-405 that pure semantic search misses.',
        },
        {
            icon: <Lock className="w-5 h-5" />,
            tag: 'Data Isolation',
            title: 'Strict tenant separation',
            description:
                'Your equipment data, fault history, and documentation never influence another customer\'s results. Isolation by architecture, not policy.',
        },
        {
            icon: <Server className="w-5 h-5" />,
            tag: 'On-Prem Ready',
            title: 'Air-gapped deployment',
            description:
                'Cloud or local LLM. Regulated facilities — pharma GMP, defense suppliers — run the same product on-premises.',
        },
    ];

    return (
        <div className="min-h-screen flex flex-col" style={{ backgroundColor: '#F5F5F7', color: '#0F172A' }}>

            {/* ── Navigation ── */}
            <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-[#E5E7EB]">
                <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
                    {/* Logo */}
                    <Link to="/" className="flex items-center gap-2 text-[#0F172A]">
                        <div className="w-8 h-8 bg-[#0F172A] rounded-lg flex items-center justify-center">
                            <Cpu className="w-4.5 h-4.5 text-white" style={{ width: '18px', height: '18px' }} />
                        </div>
                        <span className="font-bold text-lg tracking-tight">ControlsAI</span>
                    </Link>

                    {/* Right actions */}
                    <div className="flex items-center gap-3">
                        <Link
                            id="btn-open-app"
                            to="/login"
                            className="flex items-center gap-2 px-4 py-2 bg-[#0F172A] text-white text-sm font-semibold rounded-xl hover:bg-black transition-colors"
                        >
                            Open app <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                    </div>
                </div>
            </header>

            {/* ── Hero ── */}
            <main className="flex-1">
                <section className="max-w-6xl mx-auto px-6 pt-24 pb-20 text-center">
                    {/* Tag line */}
                    <p className="text-[11px] font-bold tracking-[0.2em] text-[#3B5BDB] uppercase mb-6 flex items-center justify-center gap-2">
                        <span className="inline-block w-6 h-px bg-[#3B5BDB]" />
                        Industrial AI · Manufacturing Technology
                        <span className="inline-block w-6 h-px bg-[#3B5BDB]" />
                    </p>

                    {/* Headline */}
                    <h1 className="text-5xl md:text-6xl font-extrabold text-[#0F172A] leading-[1.1] tracking-tight mb-6 max-w-3xl mx-auto">
                        Verified diagnostics.<br />
                        Safer machines.<br />
                        <span className="text-[#3B5BDB]">Zero guesswork.</span>
                    </h1>

                    {/* Subtext */}
                    <p className="text-lg text-[#64748B] max-w-xl mx-auto mb-10 leading-relaxed">
                        AI troubleshooting for factory technicians. Ask a question about your equipment — get step-by-step guidance traced to the source.
                    </p>

                    {/* CTAs */}
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                        <Link
                            id="btn-hero-open-dashboard"
                            to="/login"
                            className="flex items-center gap-2 px-6 py-3.5 bg-[#0F172A] text-white text-sm font-bold rounded-xl hover:bg-black transition-all shadow-sm hover:shadow-md"
                        >
                            Open dashboard <ArrowRight className="w-4 h-4" />
                        </Link>
                        <Link
                            id="btn-hero-signin"
                            to="/login"
                            className="flex items-center gap-2 px-6 py-3.5 bg-white text-[#0F172A] text-sm font-bold rounded-xl border border-[#E2E8F0] hover:bg-[#F8FAFC] transition-all shadow-sm"
                        >
                            Sign in
                        </Link>
                    </div>

                    {/* Trust indicators */}
                    <div className="mt-12 flex items-center justify-center gap-6 flex-wrap">
                        {['Firebase Auth', 'Qdrant Vector DB', 'Gemini 2.5 Flash', 'Cloud Run'].map(t => (
                            <span key={t} className="text-[11px] font-medium text-[#94A3B8] flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-[#94A3B8]" />
                                {t}
                            </span>
                        ))}
                    </div>
                </section>

                {/* ── How It Works ── */}
                <section className="max-w-6xl mx-auto px-6 pb-24">
                    {/* Section label */}
                    <div className="flex items-center gap-3 mb-10">
                        <span className="text-[10px] font-bold tracking-[0.2em] text-[#94A3B8] uppercase">How It Works</span>
                        <div className="flex-1 h-px bg-[#E5E7EB]" />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        {features.map((card, i) => (
                            <Card key={i} card={card} />
                        ))}
                    </div>
                </section>

                {/* ── Demo CTA Banner ── */}
                <section className="max-w-6xl mx-auto px-6 pb-20">
                    <div className="bg-[#0F172A] rounded-3xl p-10 md:p-14 flex flex-col md:flex-row items-center justify-between gap-8">
                        <div>
                            <h2 className="text-2xl md:text-3xl font-bold text-white leading-tight mb-2">
                                Ready to reduce downtime?
                            </h2>
                            <p className="text-[#94A3B8] text-sm max-w-sm">
                                Upload your project files, index your control logic, and start asking questions in minutes.
                            </p>
                        </div>
                        <Link
                            id="btn-banner-get-started"
                            to="/login"
                            className="flex-shrink-0 flex items-center gap-2 px-7 py-4 bg-white text-[#0F172A] text-sm font-bold rounded-xl hover:bg-[#F1F5F9] transition-all shadow-sm"
                        >
                            Get started free <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>
                </section>
            </main>

            {/* ── Footer ── */}
            <footer className="border-t border-[#E5E7EB] bg-white">
                <div className="max-w-6xl mx-auto px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-3">
                    <p className="text-[12px] text-[#94A3B8]">
                        ControlsAI · Verified diagnostics for factory technicians
                    </p>
                    <p className="text-[12px] text-[#94A3B8] font-mono">v0.1.0</p>
                </div>
            </footer>

        </div>
    );
}
