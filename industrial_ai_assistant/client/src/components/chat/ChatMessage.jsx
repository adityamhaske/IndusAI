import React from 'react';
import { User, Bot } from 'lucide-react';
import StructuredResponseCard from './StructuredResponseCard';

const ChatMessage = ({ message }) => {
    const isUser = message.role === 'user';

    return (
        <div className={`flex gap-4 p-4 ${isUser ? 'bg-white' : 'bg-industrial-50'} border-b border-industrial-100 last:border-0`}>
            {/* Avatar */}
            <div className={`p-2 rounded-full h-10 w-10 flex items-center justify-center flex-shrink-0 ${isUser ? 'bg-industrial-100 text-industrial-600' : 'bg-primary-100 text-primary-600'}`}>
                {isUser ? <User className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
            </div>

            {/* Content */}
            <div className="flex-1 space-y-2 overflow-hidden">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-industrial-900">{isUser ? 'Engineer' : 'Assistant'}</span>
                    <span className="text-xs text-industrial-400">{message.timestamp || 'Just now'}</span>
                </div>

                {isUser ? (
                    <p className="text-industrial-800 text-sm leading-relaxed">{message.content}</p>
                ) : (
                    // If the message content is a structured object, use the card. Otherwise text.
                    typeof message.content === 'object' ? (
                        <StructuredResponseCard data={message.content} />
                    ) : (
                        <p className="text-industrial-800 text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
                    )
                )}
            </div>
        </div>
    );
};

export default ChatMessage;
