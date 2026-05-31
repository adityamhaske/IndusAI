import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Sparkles, CheckCircle, Loader2, ArrowRight, FolderOpen } from 'lucide-react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

export const OnboardingWizard = () => {
    const navigate = useNavigate();
    const [step, setStep] = useState(1);
    
    // Check if onboarding was already completed
    const [dismissed, setDismissed] = useState(() => {
        return localStorage.getItem('controlsai_onboarding_complete') === 'true';
    });

    if (dismissed) return null;

    const handleComplete = () => {
        localStorage.setItem('controlsai_onboarding_complete', 'true');
        setDismissed(true);
        navigate('/app/project');
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden flex flex-col">
                <div className="h-1.5 w-full bg-industrial-100 flex">
                    <div className="bg-primary-600 transition-all duration-500 h-full" style={{ width: `${(step / 2) * 100}%` }} />
                </div>
                
                <div className="p-8">
                    {step === 1 && (
                        <div className="text-center animate-fade-in">
                            <div className="w-16 h-16 bg-primary-50 text-primary-600 rounded-full flex items-center justify-center mx-auto mb-6">
                                <Sparkles className="w-8 h-8" />
                            </div>
                            <h2 className="text-2xl font-bold text-industrial-900 mb-4">Welcome to ControlsAI</h2>
                            <p className="text-industrial-600 mb-8 leading-relaxed">
                                Your personal industrial AI assistant is ready. We have configured the enterprise environment for you. Let's get started analyzing logs and P&IDs.
                            </p>
                            <button
                                onClick={() => setStep(2)}
                                className="w-full flex items-center justify-center gap-2 bg-industrial-900 hover:bg-black text-white py-3 px-6 rounded-xl font-semibold transition-all"
                            >
                                Let's get started <ArrowRight className="w-5 h-5" />
                            </button>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="text-center animate-fade-in">
                            <div className="w-16 h-16 bg-green-50 text-green-600 rounded-full flex items-center justify-center mx-auto mb-6">
                                <CheckCircle className="w-8 h-8" />
                            </div>
                            <h2 className="text-2xl font-bold text-industrial-900 mb-4">All Set!</h2>
                            <p className="text-industrial-600 mb-8 leading-relaxed">
                                Your enterprise AI environment is connected. Head to the Projects page to upload your first project files and start indexing.
                            </p>
                            
                            <div className="flex flex-col gap-3">
                                <button
                                    onClick={handleComplete}
                                    className="w-full flex items-center justify-center gap-2 bg-industrial-900 hover:bg-black text-white py-3 px-6 rounded-xl font-semibold transition-all"
                                >
                                    <FolderOpen className="w-5 h-5" /> Go to Projects
                                </button>
                                <button
                                    onClick={handleComplete}
                                    className="w-full flex items-center justify-center gap-2 text-industrial-600 hover:bg-industrial-50 py-3 px-6 rounded-xl font-medium transition-all"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
