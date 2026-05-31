/**
 * App.tsx — Root component.
 *
 * Routing:
 *   Public (no auth required):
 *     /           → LandingPage
 *     /login      → LoginPage
 *
 *   Authenticated (/app/*):
 *     /app        → Chat (default)
 *     /app/chat   → Chat Assistant
 *     /app/logs   → PLC Logs
 *     /app/history → History
 *     /app/project → Project Info
 *     /app/settings → Settings
 *
 *   Legacy short paths (/chat, /logs, etc.) redirect to /app/* equivalents.
 */
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/layout/Layout'
import ChatPage from './pages/ChatPage'
import LogsPage from './pages/LogsPage'
import LoginPage from './pages/LoginPage'
import LandingPage from './pages/LandingPage'
import { ProjectPage } from './pages/ProjectPage';
import { HistoryPage } from './pages/HistoryPage';
import SettingsPage from './pages/SettingsPage'
import { Loader2 } from 'lucide-react'
import { Toaster } from 'react-hot-toast';
import { OnboardingWizard } from './components/onboarding/OnboardingWizard';
import HelpPanel from './components/layout/HelpPanel';

/**
 * Wraps authenticated /app/* routes.
 * If not logged in, redirects to the landing page.
 */
function ProtectedApp() {
    const { user, loading } = useAuth()

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-industrial-50">
                <div className="flex flex-col items-center gap-3 text-industrial-500">
                    <Loader2 className="w-8 h-8 animate-spin" />
                    <p className="text-sm font-medium">Loading ControlsAI…</p>
                </div>
            </div>
        )
    }

    if (!user) {
        return <Navigate to="/" replace />
    }

    return (
        <>
            <OnboardingWizard />
            <HelpPanel />
            <Routes>
                {/* Default /app → chat */}
                <Route index element={<Layout title="Chat Assistant"><ChatPage /></Layout>} />
                <Route path="chat" element={<Layout title="Chat Assistant"><ChatPage /></Layout>} />
                <Route path="logs" element={<Layout title="PLC Fault Logs"><LogsPage /></Layout>} />
                <Route path="history" element={<Layout title="History"><HistoryPage /></Layout>} />
                <Route path="project" element={<Layout title="Project Info"><ProjectPage /></Layout>} />
                <Route path="settings" element={<Layout title="Settings"><SettingsPage /></Layout>} />
                {/* Catch-all within /app */}
                <Route path="*" element={<Navigate to="/app/chat" replace />} />
            </Routes>
        </>
    )
}

function App() {
    return (
        <AuthProvider>
            <Toaster position="bottom-right" />
            <Router>
                <Routes>
                    {/* Public routes */}
                    <Route path="/" element={<LandingPage />} />
                    <Route path="/login" element={<LoginPage />} />

                    {/* Authenticated app routes */}
                    <Route path="/app/*" element={<ProtectedApp />} />

                    {/* Legacy redirect: /chat → /app/chat, etc. */}
                    <Route path="/chat" element={<Navigate to="/app/chat" replace />} />
                    <Route path="/logs" element={<Navigate to="/app/logs" replace />} />
                    <Route path="/history" element={<Navigate to="/app/history" replace />} />
                    <Route path="/project" element={<Navigate to="/app/project" replace />} />
                    <Route path="/settings" element={<Navigate to="/app/settings" replace />} />

                    {/* Anything else → landing */}
                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </Router>
        </AuthProvider>
    )
}

export default App
