import React, { useState, useEffect, useCallback } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout, ReportPage, DashboardPage, EvidencePage } from './pages';
import { TopBar } from './components/TopBar';
import { DemoBanner } from './components/DemoBanner';
import { usePolling } from './hooks/usePolling';
import { api } from './api';
import { DemoDirector } from './components/DemoDirector';
import { ToastContainer, Toast } from './components/Toast';

function App() {
  const [backendStatus, setBackendStatus] = useState('checking');
  const [demoToolsEnabled, setDemoToolsEnabled] = useState(false);
  const [toasts, setToasts] = useState([]);

  const checkHealth = useCallback(async () => {
    try {
      await api.health();
      setBackendStatus('connected');
    } catch {
      setBackendStatus('unavailable');
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  useEffect(() => {
    api.getFaults().then(f => setDemoToolsEnabled(f.llm_down || f.llm_malformed || f.routing_down || f.routing_slow))
      .catch(() => {});
  }, []);

  const addToast = (message, type = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000);
  };

  return (
    <div className="app">
      <DemoBanner />
      <TopBar 
        backendStatus={backendStatus} 
        demoToolsEnabled={demoToolsEnabled}
        onDemoToolsToggle={() => setDemoToolsEnabled(!demoToolsEnabled)}
      />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Navigate to="/report" replace />} />
          <Route path="/report" element={<Layout><ReportPage onToast={addToast} /></Layout>} />
          <Route path="/dashboard" element={<Layout><DashboardPage onToast={addToast} /></Layout>} />
          <Route path="/evidence" element={<Layout><EvidencePage /></Layout>} />
        </Routes>
      </main>
      <DemoDirector isOpen={demoToolsEnabled} onClose={() => setDemoToolsEnabled(false)} onToast={addToast} />
      <ToastContainer toasts={toasts} onRemove={(id) => setToasts(prev => prev.filter(t => t.id !== id))} />
    </div>
  );
}

export default App;