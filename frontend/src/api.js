const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  // Health
  health: () => request('/health'),
  summary: () => request('/summary'),

  // Incidents
  createIncident: (data) => request('/incidents', { method: 'POST', body: JSON.stringify(data) }),
  listIncidents: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.status) params.set('status', filters.status);
    if (filters.type) params.set('type', filters.type);
    return request(`/incidents?${params}`);
  },
  getIncident: (id) => request(`/incidents/${id}`),
  analyzeIncident: (id, options = {}) => request(`/incidents/${id}/analyze`, { method: 'POST', body: JSON.stringify(options) }),
  addConfirmation: (id, field, value) => request(`/incidents/${id}/confirmations`, { method: 'POST', body: JSON.stringify({ field, value }) }),
  flagIncident: (id, reason) => request(`/incidents/${id}/flag`, { method: 'POST', body: JSON.stringify({ reason }) }),
  resolveIncident: (id) => request(`/incidents/${id}/resolve`, { method: 'POST' }),
  getEvents: (id) => request(`/incidents/${id}/events`),

  // Responders
  listResponders: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.type) params.set('type', filters.type);
    if (filters.status) params.set('status', filters.status);
    return request(`/responders?${params}`);
  },

  // Recommendations
  getRecommendations: (id, faultRoutingDown = false) => {
    const params = new URLSearchParams();
    if (faultRoutingDown) params.set('fault_routing_down', 'true');
    return request(`/incidents/${id}/recommendations?${params}`);
  },

  // Dispatches
  createDispatch: (data, faultRoutingDown = false) => {
    const params = new URLSearchParams();
    if (faultRoutingDown) params.set('fault_routing_down', 'true');
    return request(`/dispatches?${params}`, { method: 'POST', body: JSON.stringify(data) });
  },
  completeDispatch: (id) => request(`/dispatches/${id}/complete`, { method: 'POST' }),
  cancelDispatch: (id) => request(`/dispatches/${id}/cancel`, { method: 'POST' }),
  listDispatches: (incidentId) => request(`/dispatches${incidentId ? `?incident_id=${incidentId}` : ''}`),

  // Demo
  getFaults: () => request('/demo/faults'),
  setFaults: (flags) => request('/demo/faults', { method: 'POST', body: JSON.stringify(flags) }),
  playScenario: (id) => request(`/demo/scenarios/${id}/play`, { method: 'POST' }),
  concurrencyProof: () => request('/demo/concurrency-proof', { method: 'POST' }),
  runEvaluation: () => request('/demo/evaluation/run', { method: 'POST' }),
  getLatestEvaluation: () => request('/demo/evaluation/latest'),
  resetDemo: () => request('/demo/reset', { method: 'POST' }),
  listScenarios: () => request('/demo/scenarios')
};