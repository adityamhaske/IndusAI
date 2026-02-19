import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import ChatPage from './pages/ChatPage'
import LogsPage from './pages/LogsPage'
import { HistoryPage, ProjectPage, SettingsPage } from './pages/Placeholders'

function App() {
    return (
        <Router>
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

export default App
