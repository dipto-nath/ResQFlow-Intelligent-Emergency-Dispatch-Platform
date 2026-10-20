import React, { useState, useEffect } from 'react';
import { 
  AlertCircle, CheckCircle, Clock, Truck, Shield, AlertTriangle, 
  MapPin, Check, X, RefreshCw, Send, CheckCheck, UserCheck, Flame, Stethoscope
} from 'lucide-react';
import { api } from '../api';

export function DashboardPage({ onToast }) {
  const [summary, setSummary] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [responders, setResponders] = useState([]);
  const [dispatches, setDispatches] = useState([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [incidentDetail, setIncidentDetail] = useState(null);
  const [recommendations, setRecommendations] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [dispatching, setDispatching] = useState(false);

  useEffect(() => {
    loadDashboardData();
    const interval = setInterval(loadDashboardData, 8000);
    return () => clearInterval(interval);
  }, [filterStatus]);

  useEffect(() => {
    if (selectedIncidentId) {
      loadIncidentDetail(selectedIncidentId);
    }
  }, [selectedIncidentId]);

  const loadDashboardData = async () => {
    try {
      const [sum, incs, resps, disps] = await Promise.all([
        api.summary().catch(() => null),
        api.listIncidents(filterStatus ? { status: filterStatus } : {}).catch(() => []),
        api.listResponders().catch(() => []),
        api.listDispatches().catch(() => [])
      ]);
      if (sum) setSummary(sum);
      setIncidents(incs || []);
      setResponders(resps || []);
      setDispatches(disps || []);
      if (!selectedIncidentId && incs?.length > 0) {
        setSelectedIncidentId(incs[0].id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const loadIncidentDetail = async (id) => {
    try {
      const [detail, recs] = await Promise.all([
        api.getIncident(id),
        api.getRecommendations(id).catch(() => null)
      ]);
      setIncidentDetail(detail);
      setRecommendations(recs);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDispatch = async (responderId) => {
    if (!selectedIncidentId) return;
    setDispatching(true);
    try {
      await api.createDispatch({
        incident_id: selectedIncidentId,
        responder_id: responderId,
        dispatcher_notes: 'Dispatched via operator dashboard'
      });
      onToast?.(`Unit #${responderId} dispatched to incident!`, 'success');
      loadDashboardData();
      loadIncidentDetail(selectedIncidentId);
    } catch (err) {
      onToast?.(`Dispatch failed: ${err.message}`, 'error');
    } finally {
      setDispatching(false);
    }
  };

  const handleResolveIncident = async (id) => {
    try {
      await api.resolveIncident(id);
      onToast?.(`Incident ${id} marked as resolved`, 'success');
      loadDashboardData();
      loadIncidentDetail(id);
    } catch (err) {
      onToast?.(`Failed to resolve incident: ${err.message}`, 'error');
    }
  };

  const handleConfirmFact = async (field, value) => {
    if (!selectedIncidentId) return;
    try {
      await api.addConfirmation(selectedIncidentId, field, value);
      onToast?.(`Fact ${field} confirmed by dispatcher`, 'success');
      loadIncidentDetail(selectedIncidentId);
    } catch (err) {
      onToast?.(`Failed to confirm fact: ${err.message}`, 'error');
    }
  };

  const handleCompleteDispatch = async (dispatchId) => {
    try {
      await api.completeDispatch(dispatchId);
      onToast?.(`Dispatch completed and responder returned to service`, 'success');
      loadDashboardData();
      if (selectedIncidentId) loadIncidentDetail(selectedIncidentId);
    } catch (err) {
      onToast?.(`Failed to complete dispatch: ${err.message}`, 'error');
    }
  };

  return (
    <div className="dashboard-page container">
      {/* Top metric tiles */}
      <section className="metrics-row">
        <div className="metric-tile">
          <span className="metric-label">Open Incidents</span>
          <span className="metric-value text-crit">{summary?.open_incidents ?? '—'}</span>
        </div>
        <div className="metric-tile">
          <span className="metric-label">Available Fleet</span>
          <span className="metric-value text-primary">{summary?.available_responders ?? '—'}</span>
        </div>
        <div className="metric-tile">
          <span className="metric-label">Active Dispatches</span>
          <span className="metric-value text-mod">{summary?.active_dispatches ?? '—'}</span>
        </div>
        <div className="metric-tile metric-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadDashboardData}>
            <RefreshCw size={14} /> Refresh Live
          </button>
        </div>
      </section>

      {/* Main dashboard columns */}
      <div className="dashboard-grid">
        {/* Left column: Incidents list */}
        <div className="incidents-sidebar">
          <div className="sidebar-header">
            <h3>Incident Queue</h3>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="filter-select"
            >
              <option value="">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="under_review">Under Review</option>
              <option value="dispatched">Dispatched</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>

          <div className="incidents-list">
            {incidents.length === 0 ? (
              <p className="empty-state">No incidents in queue</p>
            ) : (
              incidents.map((inc) => (
                <div
                  key={inc.id}
                  className={`incident-card ${selectedIncidentId === inc.id ? 'active' : ''}`}
                  onClick={() => setSelectedIncidentId(inc.id)}
                >
                  <div className="incident-card-top">
                    <span className={`priority-badge priority-${inc.priority_level?.toLowerCase() || 'mod'}`}>
                      {inc.priority_score ?? 0} • {inc.priority_level || 'PENDING'}
                    </span>
                    <span className="incident-type-tag">{inc.type.replace('_', ' ')}</span>
                  </div>
                  <p className="incident-desc-snippet">{inc.description}</p>
                  <div className="incident-card-foot">
                    <span className="incident-id mono">{inc.id}</span>
                    <span className={`status-pill status-${inc.status}`}>{inc.status}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Middle column: Selected Incident Details */}
        <div className="incident-detail-panel">
          {incidentDetail ? (
            <div className="detail-wrapper">
              <div className="detail-header">
                <div>
                  <h2>{incidentDetail.type.replace('_', ' ').toUpperCase()}</h2>
                  <span className="incident-timestamp mono">{incidentDetail.id} • {incidentDetail.created_at}</span>
                </div>
                <div className="detail-actions">
                  {incidentDetail.status !== 'resolved' && (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline"
                      onClick={() => handleResolveIncident(incidentDetail.id)}
                    >
                      <CheckCheck size={14} /> Resolve Incident
                    </button>
                  )}
                </div>
              </div>

              <div className="detail-box report-box">
                <h4>Citizen Report Narrative</h4>
                <p className="narrative-text">{incidentDetail.description}</p>
                <div className="location-tag">
                  <MapPin size={14} /> Lat: {incidentDetail.latitude}, Lng: {incidentDetail.longitude}
                </div>
              </div>

              {/* Priority calculation breakdown */}
              <div className="detail-box priority-box">
                <div className="priority-header">
                  <div>
                    <h4>Priority Assessment</h4>
                    <span className="priority-sub">
                      Floor: <strong>{incidentDetail.priority_score}</strong> / Ceiling: <strong>{incidentDetail.priority_ceiling}</strong>
                    </span>
                  </div>
                  <div className="priority-levels">
                    <span className={`priority-badge priority-${incidentDetail.priority_level?.toLowerCase()}`}>
                      {incidentDetail.priority_level}
                    </span>
                  </div>
                </div>

                {incidentDetail.priority_explanation && (
                  <p className="priority-exp">{incidentDetail.priority_explanation}</p>
                )}

                {/* Score factor items */}
                {incidentDetail.score_breakdown?.length > 0 && (
                  <div className="breakdown-list">
                    {incidentDetail.score_breakdown.map((item, idx) => (
                      <div key={idx} className="breakdown-item">
                        <span className="factor-name">{item.factor.replace('_', ' ')}</span>
                        <span className="factor-quote italic">"{item.evidence_quote || 'N/A'}"</span>
                        <span className="factor-points">+{item.points} pts</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Responder Recommendations & Dispatch Action */}
              <div className="detail-box recommendations-box">
                <h4>Recommended Units</h4>
                {recommendations?.recommendations?.length > 0 ? (
                  <div className="recommendations-list">
                    {recommendations.recommendations.map((rec) => (
                      <div key={rec.responder.id} className="rec-card">
                        <div className="rec-header">
                          <div className="rec-unit-info">
                            <strong>{rec.responder.name}</strong>
                            <span className="rec-type mono">({rec.responder.unit_type.toUpperCase()})</span>
                          </div>
                          <span className="eta-badge">{rec.eta_minutes.toFixed(1)} mins</span>
                        </div>
                        <div className="rec-details">
                          <span>Route: {rec.route_source} ({(rec.distance_meters / 1000).toFixed(2)} km)</span>
                          <span className="caps-pill">Caps: {rec.responder.capabilities?.join(', ') || 'Standard'}</span>
                        </div>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm dispatch-btn"
                          disabled={dispatching || incidentDetail.status === 'resolved'}
                          onClick={() => handleDispatch(rec.responder.id)}
                        >
                          <Send size={14} /> Dispatch Unit #{rec.responder.id}
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="empty-rec">No eligible units available or incident resolved.</p>
                )}
              </div>
            </div>
          ) : (
            <div className="no-incident-selected">
              <AlertCircle size={36} />
              <p>Select an incident from the queue to view decision support & dispatch units.</p>
            </div>
          )}
        </div>

        {/* Right column: Fleet & Active Dispatches */}
        <div className="fleet-column">
          <div className="fleet-section">
            <h3>Active Dispatches ({dispatches.length})</h3>
            <div className="dispatches-list">
              {dispatches.length === 0 ? (
                <p className="empty-state">No units actively dispatched</p>
              ) : (
                dispatches.map((disp) => (
                  <div key={disp.id} className="dispatch-item">
                    <div className="dispatch-item-top">
                      <span className="mono bold">Unit #{disp.responder_id}</span>
                      <span className="status-pill status-active">{disp.status}</span>
                    </div>
                    <div className="dispatch-item-sub">
                      <span>Inc: {disp.incident_id}</span>
                      <button
                        type="button"
                        className="btn btn-xs btn-outline"
                        onClick={() => handleCompleteDispatch(disp.id)}
                      >
                        Complete
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="fleet-section mt-4">
            <h3>Responders Fleet ({responders.length})</h3>
            <div className="responders-list">
              {responders.map((r) => (
                <div key={r.id} className="responder-item">
                  <div className="responder-row">
                    <span className="responder-name">{r.name}</span>
                    <span className={`status-pill status-${r.status}`}>{r.status}</span>
                  </div>
                  <div className="responder-meta text-xs">
                    <span>{r.unit_type}</span> • <span>{r.capabilities?.join(', ') || 'Basic'}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
