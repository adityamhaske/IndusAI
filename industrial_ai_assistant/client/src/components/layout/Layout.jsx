import React from 'react';
import Sidebar from './Sidebar';
import Header from './Header';

const Layout = ({ children, title = "Dashboard" }) => {
    return (
        <div className="flex h-screen bg-industrial-50 font-sans text-industrial-900">
            <Sidebar />
            <div className="flex-1 flex flex-col overflow-hidden relative">
                <Header title={title} />
                <main className="flex-1 overflow-hidden relative z-0">
                    {children}
                </main>
            </div>
        </div>
    );
};

export default Layout;
