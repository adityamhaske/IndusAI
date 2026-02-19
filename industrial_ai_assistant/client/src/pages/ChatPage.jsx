import React, { useState, useRef, useEffect } from 'react';
import ChatMessage from '../components/chat/ChatMessage';
import InputArea from '../components/chat/InputArea';
import { Loader2 } from 'lucide-react';

const ChatPage = () => {
    const [messages, setMessages] = useState([
        {
            role: 'assistant',
            content: 'Hello, I am ready to assist with PLC faults and commissioning. You can ask me to analyze logs or look up documentation.',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
    ]);
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSend = async (text) => {
        // Add User Message
        const userMsg = {
            role: 'user',
            content: text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        setMessages(prev => [...prev, userMsg]);
        setIsLoading(true);

        try {
            // Prepare payload for backend
            const payload = {
                message: text,
                history: messages.map(m => ({ role: m.role, content: typeof m.content === 'object' ? JSON.stringify(m.content) : m.content }))
            };

            // Call backend API
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error('API Error');
            const data = await response.json();

            // Add Assistant Message (data is expected to be ChatResponse)
            const botMsg = {
                role: 'assistant',
                content: data, // Structured object
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            };
            setMessages(prev => [...prev, botMsg]);

        } catch (error) {
            console.error("Chat Error:", error);
            // Fallback error message
            const errorMsg = {
                role: 'assistant',
                content: "I encountered an error processing your request. Please check the backend connection.",
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            };
            setMessages(prev => [...prev, errorMsg]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-industrial-50">
            {/* Chat Messages Area */}
            <div className="flex-1 overflow-y-auto">
                <div className="max-w-4xl mx-auto w-full bg-white shadow-sm min-h-full border-x border-industrial-200">
                    {messages.map((msg, index) => (
                        <ChatMessage key={index} message={msg} />
                    ))}

                    {isLoading && (
                        <div className="p-6 flex items-center gap-3 text-industrial-500 bg-industrial-50 border-b border-industrial-100 animate-pulse">
                            <Loader2 className="w-5 h-5 animate-spin" />
                            <span className="text-sm font-medium">Analyzing Documentation and Logs...</span>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>
            </div>

            {/* Input Area */}
            <div className="bg-white border-t border-industrial-200">
                <div className="max-w-4xl mx-auto w-full border-x border-industrial-200">
                    <InputArea onSend={handleSend} isLoading={isLoading} />
                </div>
            </div>
        </div>
    );
};

export default ChatPage;
