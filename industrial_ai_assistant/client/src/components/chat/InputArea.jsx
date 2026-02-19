import React, { useState, useRef, useEffect } from 'react';
import { Send, StopCircle, Paperclip } from 'lucide-react';

const InputArea = ({ onSend, isLoading, onStop }) => {
    const [text, setText] = useState('');
    const textareaRef = useRef(null);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (text.trim() && !isLoading) {
            onSend(text);
            setText('');
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    };

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 150) + 'px';
        }
    }, [text]);

    return (
        <div className="p-4 bg-white border-t border-industrial-200">
            <form onSubmit={handleSubmit} className="card-shadow-lg rounded-xl border border-industrial-300 bg-white flex flex-col overflow-hidden focus-within:ring-2 focus-within:ring-primary-500 focus-within:border-primary-500 transition-shadow">
                <textarea
                    ref={textareaRef}
                    rows={1}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Describe the fault, ask for documentation, or upload a log..."
                    className="w-full p-4 resize-none outline-none text-sm text-industrial-800 placeholder:text-industrial-400 max-h-[150px]"
                />

                <div className="px-4 py-2 bg-industrial-50 border-t border-industrial-100 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <button type="button" className="p-2 text-industrial-400 hover:text-industrial-600 hover:bg-industrial-200 rounded-md transition-colors" title="Attach Log">
                            <Paperclip className="w-4 h-4" />
                        </button>
                    </div>

                    <div className="flex items-center gap-3">
                        <span className="text-xs text-industrial-400 hidden sm:inline">Press <kbd className="font-sans px-1 py-0.5 rounded border border-industrial-300 bg-white">Enter</kbd> to send</span>
                        {isLoading ? (
                            <button type="button" onClick={onStop} className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md text-sm font-medium transition-colors">
                                <StopCircle className="w-4 h-4" />
                                Stop
                            </button>
                        ) : (
                            <button type="submit" disabled={!text.trim()} className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-industrial-300 disabled:text-industrial-500 text-white rounded-md text-sm font-medium transition-colors">
                                Send
                                <Send className="w-4 h-4" />
                            </button>
                        )}
                    </div>
                </div>
            </form>
        </div>
    );
};

export default InputArea;
