import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapPin, AlertCircle, CheckCircle, Loader2, XCircle } from 'lucide-react';
import { api } from '../api';
import { LocationPicker } from '../components/LocationPicker';

const INCIDENT_TYPES = [
  { value: 'road_accident', label: 'Road Accident', description: 'Vehicle collision, pedestrian incident' },
  { value: 'fire', label: 'Fire', description: 'Structure fire, vehicle fire, wildfire' },
  { value: 'medical_emergency', label: 'Medical Emergency', description: 'Cardiac arrest, unconscious, breathing difficulty' },
  { value: 'other', label: 'Other', description: 'Any other emergency situation' }
];

const PRESET_LOCATIONS = [
  { name: 'Near Flyover (S1/S6)', lat: 22.5726, lng: 88.3639 },
  { name: 'Crossing (S2)', lat: 22.5800, lng: 88.3700 },
  { name: 'Restaurant Area (S3)', lat: 22.5600, lng: 88.3500 },
  { name: 'Bus Stand (S4)', lat: 22.5900, lng: 88.3800 },
  { name: 'Multi-vehicle Zone (S5)', lat: 22.5750, lng: 88.3650 },
  { name: 'Shop District (S7/S8)', lat: 22.5650, lng: 88.3550 },
];

export function ReportPage({ onToast }) {
  const navigate = useNavigate();
  const [step, setStep] = useState('form');
  const [formData, setFormData] = useState({
    type: 'road_accident',
    description: '',
    latitude: '',
    longitude: ''
  });
  const [errors, setErrors] = useState({});
  const [submittedIncident, setSubmittedIncident] = useState(null);
  const [charCount, setCharCount] = useState(0);
  const mapRef = useRef(null);
  const [map, setMap] = useState(null);
  const [marker, setMarker] = useState(null);

  useEffect(() => {
    if (mapRef.current && !map) {
      import('leaflet').then(L => {
        const newMap = L.map(mapRef.current, {
          center: [22.5726, 88.3639],
          zoom: 12,
          zoomControl: false
        });
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
          maxZoom: 19
        }).addTo(newMap);
        setMap(newMap);
        newMap.on('click', (e) => {
          const { lat, lng } = e.latlng;
          setFormData(prev => ({ ...prev, latitude: lat.toFixed(6), longitude: lng.toFixed(6) }));
          updateMarker(lat, lng);
        });
      });
    }
  }, [map]);

  const updateMarker = (lat, lng) => {
    if (!map) return;
    import('leaflet').then(L => {
      if (marker) map.removeLayer(marker);
      const newMarker = L.circleMarker([lat, lng], {
        radius: 10,
        color: '#2F7F79',
        fillColor: '#2F7F79',
        fillOpacity: 1,
        weight: 3
      }).addTo(map);
      setMarker(newMarker);
    });
  };

  const validateForm = () => {
    const newErrors = {};
    if (!formData.description.trim() || formData.description.trim().length < 10) {
      newErrors.description = 'Description must be at least 10 characters';
    }
    if (formData.description.length > 2000) {
      newErrors.description = 'Description must not exceed 2000 characters';
    }
    const lat = parseFloat(formData.latitude);
    const lng = parseFloat(formData.longitude);
    if (isNaN(lat) || lat < -90 || lat > 90) {
      newErrors.latitude = 'Latitude must be between -90 and 90';
    }
    if (isNaN(lng) || lng < -180 || lng > 180) {
      newErrors.longitude = 'Longitude must be between -180 and 180';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;
    setStep('submitting');
    try {
      const result = await api.createIncident({
        type: formData.type,
        description: formData.description.trim(),
        latitude: parseFloat(formData.latitude),
        longitude: parseFloat(formData.longitude)
      });
      setSubmittedIncident(result);
      setStep('success');
      onToast?.('Incident submitted successfully', 'success');
    } catch (err) {
      setStep('error');
      onToast?.(err.message, 'error');
    }
  };

  const handleDescriptionChange = (e) => {
    const value = e.target.value;
    setFormData(prev => ({ ...prev, description: value }));
    setCharCount(value.length);
  };

  const handlePresetLocation = (loc) => {
    setFormData(prev => ({ ...prev, latitude: loc.lat.toFixed(6), longitude: loc.lng.toFixed(6) }));
    updateMarker(loc.lat, loc.lng);
  };

  const handleViewDashboard = () => navigate('/dashboard');
  const handleNewReport = () => {
    setFormData({ type: 'road_accident', description: '', latitude: '', longitude: '' });
    setStep('form');
    setSubmittedIncident(null);
    setCharCount(0);
  };
  const handleTryAgain = () => setStep('form');

  if (step === 'success') {
    return (
      <div className="report-page success-state">
        <div className="success-card">
          <div className="success-icon"><CheckCircle size={64} /></div>
          <h1>Incident Submitted</h1>
          <div className="incident-details">
            <div className="detail-row"><span className="detail-label">Incident ID</span><span className="detail-value mono">{submittedIncident.id}</span></div>
            <div className="detail-row"><span className="detail-label">Status</span><span className="detail-value"><span className="status-badge status-pending">Pending</span></span></div>
            <div className="detail-row"><span className="detail-label">Submitted</span><span className="detail-value mono">{new Date(submittedIncident.created_at).toLocaleString()}</span></div>
          </div>
          <p className="disclaimer"><AlertCircle size={16} /> No emergency service was contacted. In a real emergency in India, call <strong>112</strong>.</p>
          <div className="success-actions">
            <button className="btn btn-primary" onClick={handleViewDashboard}>View in Dispatcher Dashboard</button>
            <button className="btn btn-secondary" onClick={handleNewReport}>Submit Another Report</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="report-page">
      <div className="page-header">
        <h1>Report an Incident</h1>
        <p className="page-subtitle">Submit a simulated emergency report for dispatcher review. All data is synthetic — no real services are contacted.</p>
      </div>

      <form onSubmit={handleSubmit} className="incident-form" noValidate>
        <fieldset className="form-section">
          <legend>Incident Type</legend>
          <div className="type-options">
            {INCIDENT_TYPES.map(type => (
              <label key={type.value} className={'type-option ' + (formData.type === type.value ? 'selected' : '')}>
                <input type="radio" name="type" value={type.value} checked={formData.type === type.value} onChange={(e) => setFormData(prev => ({ ...prev, type: e.target.value }))} disabled={step === 'submitting'} />
                <div className="type-option-content"><span className="type-label">{type.label}</span><span className="type-desc">{type.description}</span></div>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="form-section">
          <legend>Description</legend>
          <textarea value={formData.description} onChange={handleDescriptionChange} placeholder="Describe the incident... e.g., 'A rider has fallen after a collision near the flyover. One person is unconscious and there is a fuel leak from the bike.'" rows={4} maxLength={2000} disabled={step === 'submitting'} aria-describedby="char-count description-error" aria-invalid={!!errors.description} />
          <div className="textarea-footer">
            <span id="char-count" className={'char-count ' + (charCount > 1800 ? 'warning' : '')}>{charCount} / 2000 characters</span>
            {errors.description && <span id="description-error" className="field-error" role="alert"><XCircle size={14} /> {errors.description}</span>}
          </div>
        </fieldset>

        <fieldset className="form-section">
          <legend>Location</legend>
          <LocationPicker formData={formData} setFormData={setFormData} mapRef={mapRef} presetLocations={PRESET_LOCATIONS} onPresetSelect={handlePresetLocation} disabled={step === 'submitting'} errors={errors} />
        </fieldset>

        <div className="form-actions">
          <button type="submit" className="btn btn-primary btn-lg" disabled={step === 'submitting'}>
            {step === 'submitting' && <Loader2 size={20} className="spinning" />}{step === 'submitting' ? 'Submitting...' : 'Submit Incident'}
          </button>
          <p className="submit-disclaimer"><AlertCircle size={14} /> No emergency service will be contacted. This is a simulation.</p>
        </div>
      </form>

      {step === 'error' && (
        <div className="error-state" role="alert">
          <AlertCircle size={48} className="error-icon" />
          <h2>Submission Failed</h2>
          <p>Unable to submit incident. Please check your connection and try again.</p>
          <button className="btn btn-primary" onClick={handleTryAgain}>Try Again</button>
        </div>
      )}
    </div>
  );
}