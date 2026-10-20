import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { MapPin, Settings, AlertTriangle, Circle, Wifi, WifiOff } from 'lucide-react';

export function TopBar({ 
  backendStatus, 
  demoToolsEnabled, 
  onDemoToolsToggle 
}) {
  const location = useLocation();
  const isDashboard = location.pathname === '/dashboard';
  const isEvidence = location.pathname === '/evidence';

  return (
    <header className="top-bar" role="banner">
      <div className="top-bar-left">
        <div className="brand">
          <Circle className="brand-icon" size={28} />
          <span className="brand-text">Sahayak Dispatch</span>
        </div>
        <span className="demo-badge">DEMO / SIMULATED</span>
      </div>

      <nav className="top-bar-nav" aria-label="Main navigation">
        <Link 
          to="/report" 
          className={`nav-link ${!isDashboard && !isEvidence ? 'active' : ''}`}
          aria-current={!isDashboard && !isEvidence ? 'page' : undefined}
        >
          <MapPin size={18} /> Report Incident
        </Link>
        <Link 
          to="/dashboard" 
          className={`nav-link ${isDashboard ? 'active' : ''}`}
          aria-current={isDashboard ? 'page' : undefined}
        >
          Dispatcher Dashboard
        </Link>
        <Link 
          to="/evidence" 
          className={`nav-link ${isEvidence ? 'active' : ''}`}
          aria-current={isEvidence ? 'page' : undefined}
        >
          Evidence
        </Link>
      </nav>

      <div className="top-bar-right">
        <div className="backend-status" aria-live="polite">
          {backendStatus === 'checking' && (
            <span className="status-checking">
              <span className="spinner" aria-hidden="true"></span>
              Checking...
            </span>
          )}
          {backendStatus === 'connected' && (
            <span className="status-connected">
              <Wifi size={16} /> Backend connected
            </span>
          )}
          {backendStatus === 'unavailable' && (
            <span className="status-error">
              <WifiOff size={16} /> Backend unavailable
            </span>
          )}
        </div>

        {demoToolsEnabled && (
          <div className="active-faults" aria-live="polite">
            <AlertTriangle size={16} className="fault-icon" />
            <span>Active simulated fault</span>
          </div>
        )}

        <button 
          className="demo-tools-toggle"
          onClick={onDemoToolsToggle}
          aria-expanded={demoToolsEnabled}
          aria-controls="demo-director"
          aria-label={demoToolsEnabled ? 'Hide demo tools' : 'Show demo tools'}
        >
          <Settings size={20} />
          <span className="toggle-text">Demo Tools</span>
          {demoToolsEnabled && <span className="toggle-indicator" aria-hidden="true"></span>}
        </button>
      </div>
    </header>
  );
}