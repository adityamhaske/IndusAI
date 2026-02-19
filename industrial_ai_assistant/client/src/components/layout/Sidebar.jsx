import React from 'react';
import { NavLink } from 'react-router-dom';
import { MessageSquare, FileText, History, Settings, Box, PlusCircle } from 'lucide-react';

const Sidebar = () => {
    const navItems = [
        { to: '/chat', icon: MessageSquare, label: 'Chat Assistant' },
        { to: '/logs', icon: FileText, label: 'PLC Logs' },
        { to: '/history', icon: History, label: 'History' },
        { to: '/project', icon: Box, label: 'Project Info' },
        { to: '/settings', icon: Settings, label: 'Settings' },
    ];

    return (
        <aside className="w-72 bg-white border-r border-industrial-200 flex flex-col h-full shadow-sm z-10 transition-all duration-300">
            {/* Logo Area */}
            <div className="h-16 flex items-center px-6 border-b border-industrial-100">
                <div className="flex items-center gap-2 text-industrial-900">
                    <Box className="w-6 h-6 text-primary-600" />
                    <span className="font-bold text-lg tracking-tight">IndusAI</span>
                </div>
            </div>

            {/* Project Info Placeholder */}
            <div className="gx-6 p-4 m-4 bg-industrial-50 rounded-lg border border-industrial-200">
                <div className="text-xs font-medium text-industrial-500 uppercase mb-1">Active Project</div>
                <div className="font-semibold text-industrial-800 text-sm truncate">Commissioning V1</div>
                <div className="flex items-center gap-2 mt-2">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                        Indexed
                    </span>
                    <span className="text-xs text-industrial-400">v1.2</span>
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 px-4 space-y-1 overflow-y-auto py-2">
                <div className="text-xs font-semibold text-industrial-400 px-2 py-2">MENU</div>
                {navItems.map((item) => (
                    <NavLink
                        key={item.to}
                        to={item.to}
                        className={({ isActive }) =>
                            `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors duration-200 group ${isActive
                                ? 'bg-primary-50 text-primary-700'
                                : 'text-industrial-600 hover:bg-industrial-50 hover:text-industrial-900'
                            }`
                        }
                    >
                        <item.icon className={`w-5 h-5 transition-colors ${({ isActive }) => isActive ? 'text-primary-600' : 'text-industrial-400 group-hover:text-industrial-600'}`} />
                        {item.label}
                    </NavLink>
                ))}
            </nav>

            {/* New Session Button */}
            <div className="p-4 border-t border-industrial-200">
                <button className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 text-white py-2.5 px-4 rounded-lg font-medium transition-colors shadow-sm text-sm">
                    <PlusCircle className="w-4 h-4" />
                    New Chat Session
                </button>
            </div>

        </aside>
    );
};

export default Sidebar;
