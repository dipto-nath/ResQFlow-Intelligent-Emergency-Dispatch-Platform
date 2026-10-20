import React from 'react';
import { MapPin, Navigation, Compass } from 'lucide-react';

export function LocationPicker({
  formData,
  setFormData,
  mapRef,
  presetLocations,
  onPresetSelect,
  disabled,
  errors
}) {
  return (
    <div className="location-picker">
      <div className="preset-locations">
        <span className="preset-title">
          <Compass size={14} /> Quick Demo Locations:
        </span>
        <div className="preset-chips">
          {presetLocations.map((preset) => (
            <button
              key={preset.name}
              type="button"
              className="preset-chip"
              onClick={() => onPresetSelect(preset)}
              disabled={disabled}
            >
              <MapPin size={12} /> {preset.name}
            </button>
          ))}
        </div>
      </div>

      <div className="map-wrapper">
        <div ref={mapRef} className="map-container" style={{ height: '240px', width: '100%', borderRadius: '8px' }} />
        <div className="map-hint">Click on map to position incident pin</div>
      </div>

      <div className="coords-inputs">
        <div className="coords-field">
          <label htmlFor="latitude">Latitude</label>
          <input
            id="latitude"
            type="number"
            step="any"
            value={formData.latitude}
            onChange={(e) => setFormData(prev => ({ ...prev, latitude: e.target.value }))}
            placeholder="e.g. 22.5726"
            disabled={disabled}
          />
        </div>
        <div className="coords-field">
          <label htmlFor="longitude">Longitude</label>
          <input
            id="longitude"
            type="number"
            step="any"
            value={formData.longitude}
            onChange={(e) => setFormData(prev => ({ ...prev, longitude: e.target.value }))}
            placeholder="e.g. 88.3639"
            disabled={disabled}
          />
        </div>
      </div>
      {errors?.location && (
        <span className="field-error" role="alert">{errors.location}</span>
      )}
    </div>
  );
}
