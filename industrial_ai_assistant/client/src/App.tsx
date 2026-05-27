/**
 * App.tsx — Root component with Firebase Auth gate.
 *
 * Shows LoginPage when not authenticated.
 * Shows the main app layout when authenticated.
 */
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/layout/Layout'
import ChatPage from './pages/ChatPage'
import LogsPage from './pages/LogsPage'
import LoginPage from './pages/LoginPage'
import { ProjectPage } from './pages/ProjectPage';
import { HistoryPage } from './pages/HistoryPage';
import SettingsPage from './pages/SettingsPage'
import { Loader2 } from 'lucide-react'
import { Toaster } from 'react-hot-toast';
import { OnboardingWizard } from './components/onboarding/OnboardingWizard';
import HelpPanel from './components/layout/HelpPanel';

function AuthGate() {
    const { user, loading } = useAuth()

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-industrial-50">
                <div className="flex flex-col items-center gap-3 text-industrial-500">
                    <Loader2 className="w-8 h-8 animate-spin" />
                    <p className="text-sm font-medium">Loading IndusAI…</p>
                </div>
            </div>
        )
    }

    if (!user) {
        return <LoginPage />
    }

    return (
        <Router>
            <OnboardingWizard />
            <HelpPanel />
            <Routes>
                <Route path="/" element={<Layout title="Chat Assistant"><ChatPage /></Layout>} />
                <Route path="/chat" element={<Layout title="Chat Assistant"><ChatPage /></Layout>} />
                <Route path="/logs" element={<Layout title="PLC Fault Logs"><LogsPage /></Layout>} />
                <Route path="/history" element={<Layout title="History"><HistoryPage /></Layout>} />
                <Route path="/project" element={<Layout title="Project Info"><ProjectPage /></Layout>} />
                <Route path="/settings" element={<Layout title="Settings"><SettingsPage /></Layout>} />
                <Route path="*" element={<Navigate to="/chat" replace />} />
            </Routes>
        </Router>
    )
}

function App() {
    return (
        <AuthProvider>
            <Toaster position="bottom-right" />
            <AuthGate />
        </AuthProvider>
    )
}

export default App
