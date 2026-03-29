import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import ErrorBoundary from './components/ErrorBoundary';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import StartSession from './pages/StartSession';
import ActiveSession from './pages/ActiveSession';
import SessionHistory from './pages/SessionHistory';
import SessionDetail from './pages/SessionDetail';
import StudyClawChat from './pages/StudyClawChat';

function App() {

    return (
        <QueryClientProvider client={queryClientInstance}>
            <ErrorBoundary>
                <Router>
                    <Routes>
                        <Route element={<Layout />}>
                            <Route path="/" element={<Dashboard />} />
                            <Route path="/session/start" element={<StartSession />} />
                            <Route path="/session/active" element={<ActiveSession />} />
                            <Route path="/history" element={<SessionHistory />} />
                            <Route path="/history/:sessionId" element={<SessionDetail />} />
                            <Route path="/chat" element={<StudyClawChat />} />
                            <Route path="*" element={<PageNotFound />} />
                        </Route>
                    </Routes>
                </Router>
            </ErrorBoundary>
            <Toaster />
        </QueryClientProvider>
    )
}

export default App
