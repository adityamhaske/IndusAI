import React, { useState, useEffect } from 'react';
import { X, Book, MessageSquare, Terminal, Settings } from 'lucide-react';

const HelpPanel = () => {
    const [isOpen, setIsOpen] = useState(false);

    useEffect(() => {
        const handleOpen = () => setIsOpen(true);
        document.addEventListener('open-help', handleOpen);
        return () => document.removeEventListener('open-help', handleOpen);
    }, []);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex justify-end overflow-hidden">
            <div
                className="absolute inset-0 bg-industrial-900/20 backdrop-blur-sm transition-opacity"
                onClick={() => setIsOpen(false)}
            />
            
            <div className="relative w-full max-w-[400px] bg-white shadow-2xl h-full flex flex-col animate-slide-in-right border-l border-industrial-200">
                <div className="flex items-center justify-between p-5 border-b border-industrial-100 bg-industrial-50">
                    <h2 className="text-lg font-bold text-industrial-900 flex items-center gap-2">
                        <Book className="w-5 h-5 text-primary-600" />
                        Help & Documentation
                    </h2>
                    <button
                        onClick={() => setIsOpen(false)}
                        className="p-2 text-industrial-400 hover:text-industrial-700 hover:bg-industrial-200 rounded-full transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-8 text-sm text-industrial-700">
                    
                    <section>
                        <h3 className="text-base font-semibold text-industrial-900 mb-3 flex items-center gap-2">
                            <MessageSquare className="w-4 h-4 text-industrial-500" />
                            Chatting with IndusAI
                        </h3>
                        <p className="mb-3 leading-relaxed">
                            IndusAI can answer complex questions about your PLC logic. Try asking things like:
                        </p>
                        <ul className="list-disc pl-5 space-y-2 text-industrial-600">
                            <li>"What are the interlocks for PUMP_101?"</li>
                            <li>"Why did the main conveyor fault?"</li>
                            <li>"Summarize the auto-sequence logic."</li>
                        </ul>
                    </section>

                    <section>
                        <h3 className="text-base font-semibold text-industrial-900 mb-3 flex items-center gap-2">
                            <Terminal className="w-4 h-4 text-industrial-500" />
                            Analyzing Fault Logs
                        </h3>
                        <p className="mb-3 leading-relaxed">
                            Navigate to the <strong>PLC Logs</strong> tab to upload SCADA exports or telemetry data. 
                            IndusAI will correlate faults with your control logic to find the root cause.
                        </p>
                    </section>

                    <section>
                        <h3 className="text-base font-semibold text-industrial-900 mb-3 flex items-center gap-2">
                            <Settings className="w-4 h-4 text-industrial-500" />
                            Projects & Indexing
                        </h3>
                        <p className="mb-3 leading-relaxed">
                            Go to <strong>Project Info</strong> to upload your L5X, PDF, or DXF files. IndusAI embeds these files into a vector database so it can reference them when answering.
                        </p>
                    </section>
                </div>
                
                <div className="p-5 border-t border-industrial-100 bg-industrial-50 text-xs text-industrial-500 text-center">
                    IndusAI Assistant v1.0
                </div>
            </div>
        </div>
    );
};

export default HelpPanel;
