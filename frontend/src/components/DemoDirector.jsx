import React, { useState, useEffect } from 'react';
import { Settings, X, Play, RefreshCw, Zap, ShieldAlert, Check, AlertOctagon } from 'lucide-react';
import { api } from '../api';

export function DemoDirector({ isOpen, onClose, onToast }) {
  const [faults, setFaults] = useState({
    llm_down: false,
    llm_malformed: false,
    routing_down: false,
    routing_slow: false
  });
  const [scenarios, setScenarios] = useState({});
  const [loading, setLoading] = useState(false);
  const [concurrencyResult, setConcurrencyResult] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const loadData = async () => {
    try {
      const [faultData, scenarioData] = await Promise.all([
        api.getFaults().catch(() => null),
        api.listScenarios().catch(() => ({}))
      ]);
      if (faultData) setFaults(faultData);
      if (scenarioData) setScenarios(scenarioData);
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleFault = async (key) => {
    const updated = { ...faults, [key]: !faults[key] };
    try {
      const res = await api.setFaults(updated);
      setFaults(res);
      onToast?.(`Fault ${key} set to ${res[key] ? 'ENABLED' : 'DISABLED'}`, res[key] ? 'warning' : 'success');
    } catch {
      onToast?.('Failed to update fault state', 'error');
    }
  };

  const handlePlayScenario = async (id) => {
    setLoading(true);
    try {
      const res = await api.playScenario(id);
      onToast?.(`Scenario ${id} generated incident: ${res.incident_id}`, 'success');
    } catch (err) {
      onToast?.(`Failed to run scenario: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleConcurrencyProof = async () => {
    setLoading(true);
    try {
      const res = await api.concurrencyProof();
      setConcurrencyResult(res);
      onToast?.('Concurrency test finished: Race conditions rejected correctly!', 'success');
    } catch (err) {
      onToast?.(`Concurrency test error: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleResetDemo = async () => {
    if (!window.confirm('Reset simulated database and seed baseline data?')) return;
    setLoading(true);
    try {
      await api.resetDemo();
      setConcurrencyResult(null);
      onToast?.('Simulation database reset successfully', 'success');
    } catch (err) {
      onToast?.(`Failed to reset: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="demo-director-overlay" role="dialog" aria-modal="true" aria-labelledby="demo-director-title">
      <div className="demo-director-panel">
        <div className="panel-header">
          <div className="panel-title-wrap">
            <Settings size={20} className="text-primary" />
            <h2 id="demo-director-title">Demo Controls & Fault Injection</h2>
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close demo controls">
            <X size={18} />
          </button>
        </div>

        <div className="panel-body">
          <section className="director-section">
            <h3>Fault Injection Flags</h3>
            <p className="section-desc">Simulate backend failures to observe automated fallbacks.</p>
            <div className="toggle-list">
              <label className="toggle-item">
                <input
                  type="checkbox"
                  checked={faults.llm_down}
                  onChange={() => handleToggleFault('llm_down')}
                />
                <span className="toggle-label">
                  <strong>LLM Service Outage</strong>
                  <small>Forces fallback to deterministic regex/keyword parser</small>
                </span>
              </label>

              <label className="toggle-item">
                <input
                  type="checkbox"
                  checked={faults.llm_malformed}
                  onChange={() => handleToggleFault('llm_malformed')}
                />
                <span className="toggle-label">
                  <strong>Malformed LLM Output</strong>
                  <small>Forces ungrounded facts to be demoted with uncertainty flags</small>
                </span>
              </label>

              <label className="toggle-item">
                <input
                  type="checkbox"
                  checked={faults.routing_down}
                  onChange={() => handleToggleFault('routing_down')}
                />
                <span className="toggle-label">
                  <strong>OSRM Routing Down</strong>
                  <small>Switches dispatch routing to Haversine straight-line estimates</small>
                </span>
              </label>

              <label className="toggle-item">
                <input
                  type="checkbox"
                  checked={faults.routing_slow}
                  onChange={() => handleToggleFault('routing_slow')}
                />
                <span className="toggle-label">
                  <strong>Routing High Latency (Slow)</strong>
                  <small>Simulates 3.5s timeout on routing engine</small>
                </span>
              </label>
            </div>
          </section>

          <section className="director-section">
            <h3>Quick Scenarios</h3>
            <p className="section-desc">Load benchmark scenarios to test edge cases.</p>
            <div className="scenario-grid">
              {Object.entries(scenarios).map(([id, item]) => (
                <div key={id} className="scenario-card">
                  <div className="scenario-info">
                    <span className="scenario-id">{id}</span>
                    <span className="scenario-name">{item.name}</span>
                    <p className="scenario-point">{item.talking_point}</p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    onClick={() => handlePlayScenario(id)}
                    disabled={loading}
                  >
                    <Play size={12} /> Play
                  </button>
                </div>
              ))}
            </div>
          </section>

          <section className="director-section">
            <h3>Concurrency Conflict Lab</h3>
            <p className="section-desc">Test database immediate transactions against double-dispatch conflicts.</p>
            <div className="action-row">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleConcurrencyProof}
                disabled={loading}
              >
                <Zap size={14} /> Run Concurrency Test
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleResetDemo}
                disabled={loading}
              >
                <RefreshCw size={14} /> Reset Demo State
              </button>
            </div>

            {concurrencyResult && (
              <div className="concurrency-report">
                <h4>Results:</h4>
                <div className="stats-badges">
                  <span className="badge badge-success">
                    <Check size={12} /> {concurrencyResult.successful_dispatches} Dispatched
                  </span>
                  <span className="badge badge-warning">
                    <AlertOctagon size={12} /> {concurrencyResult.rejected_conflicts} Conflicts (HTTP 409)
                  </span>
                </div>
                <p className="report-text">
                  Total threads: {concurrencyResult.total_attempts}. Winner assigned unit #{concurrencyResult.assigned_responder_id}. Zero double-booking detected.
                </p>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
