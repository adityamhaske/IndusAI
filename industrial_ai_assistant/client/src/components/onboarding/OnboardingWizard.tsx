import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { userApi } from '../../services/userApi';
import { projectApi } from '../../services/projectApi';
import { Sparkles, Key, CheckCircle, Loader2, ArrowRight } from 'lucide-react';
import toast from 'react-hot-toast';

export const OnboardingWizard = () => {
    const { hasApiKey, refreshSettings } = useAuth();
    const [step, setStep] = useState(1);
    const [apiKey, setApiKey] = useState('');
    const [isSaving, setIsSaving] = useState(false);
    const [isCreatingDemo, setIsCreatingDemo] = useState(false);

    // If they have the key, and they finish, or if they close it, we unmount
    const [dismissed, setDismissed] = useState(false);

    if (hasApiKey || dismissed) return null;

    const handleSaveKey = async () => {
        if (!apiKey.trim()) return;
        setIsSaving(true);
        try {
            await userApi.saveSettings({ llm_provider: 'gemini', llm_api_key: apiKey.trim() });
            await refreshSettings();
            toast.success('API Key saved successfully!');
            setStep(3);
        } catch (error: any) {
            toast.error('Failed to save API key.');
        } finally {
            setIsSaving(false);
        }
    };

    const handleCreateDemo = async () => {
        setIsCreatingDemo(true);
        try {
            await projectApi.createProject('demo', 'Demo Project');
            toast.success('Demo project created!');
            setDismissed(true);
        } catch (error: any) {
            toast.error('Failed to create demo project.');
        } finally {
            setIsCreatingDemo(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden flex flex-col">
                <div className="h-1.5 w-full bg-industrial-100 flex">
                    <div className="bg-primary-600 transition-all duration-500 h-full" style={{ width: `${(step / 3) * 100}%` }} />
                </div>
                
                <div className="p-8">
                    {step === 1 && (
                        <div className="text-center animate-fade-in">
                            <div className="w-16 h-16 bg-primary-50 text-primary-600 rounded-full flex items-center justify-center mx-auto mb-6">
                                <Sparkles className="w-8 h-8" />
                            </div>
                            <h2 className="text-2xl font-bold text-industrial-900 mb-4">Welcome to IndusAI</h2>
                            <p className="text-industrial-600 mb-8 leading-relaxed">
                                Your personal industrial AI assistant. Before we get started analyzing logs and P&IDs, you need to configure your Gemini API key.
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
                        <div className="animate-fade-in">
                            <div className="flex items-center gap-4 mb-6">
                                <div className="w-12 h-12 bg-industrial-100 text-industrial-700 rounded-full flex items-center justify-center">
                                    <Key className="w-6 h-6" />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold text-industrial-900">Configure API Key</h2>
                                    <p className="text-sm text-industrial-500">Bring your own Gemini API key</p>
                                </div>
                            </div>
                            
                            <div className="mb-8">
                                <label className="block text-sm font-medium text-industrial-700 mb-2">Gemini API Key</label>
                                <input
                                    type="password"
                                    value={apiKey}
                                    onChange={(e) => setApiKey(e.target.value)}
                                    placeholder="AIzaSy..."
                                    className="w-full px-4 py-3 border border-industrial-200 rounded-xl focus:ring-2 focus:ring-industrial-500 focus:border-transparent outline-none transition-all"
                                />
                                <p className="text-xs text-industrial-500 mt-2">
                                    Your key is stored securely in Firebase and only used for your requests.
                                </p>
                            </div>

                            <button
                                onClick={handleSaveKey}
                                disabled={!apiKey.trim() || isSaving}
                                className="w-full flex items-center justify-center gap-2 bg-industrial-900 hover:bg-black disabled:bg-industrial-300 text-white py-3 px-6 rounded-xl font-semibold transition-all"
                            >
                                {isSaving ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Save & Continue'}
                            </button>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="text-center animate-fade-in">
                            <div className="w-16 h-16 bg-green-50 text-green-600 rounded-full flex items-center justify-center mx-auto mb-6">
                                <CheckCircle className="w-8 h-8" />
                            </div>
                            <h2 className="text-2xl font-bold text-industrial-900 mb-4">All Set!</h2>
                            <p className="text-industrial-600 mb-8 leading-relaxed">
                                You're ready to use IndusAI. Would you like to create a demo project to explore the features?
                            </p>
                            
                            <div className="flex flex-col gap-3">
                                <button
                                    onClick={handleCreateDemo}
                                    disabled={isCreatingDemo}
                                    className="w-full flex items-center justify-center gap-2 bg-industrial-900 hover:bg-black disabled:bg-industrial-300 text-white py-3 px-6 rounded-xl font-semibold transition-all"
                                >
                                    {isCreatingDemo ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Create Demo Project'}
                                </button>
                                <button
                                    onClick={() => setDismissed(true)}
                                    className="w-full flex items-center justify-center gap-2 text-industrial-600 hover:bg-industrial-50 py-3 px-6 rounded-xl font-medium transition-all"
                                >
                                    Skip for now
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
