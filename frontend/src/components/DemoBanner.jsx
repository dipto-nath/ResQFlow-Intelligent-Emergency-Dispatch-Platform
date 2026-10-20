import React from 'react';
import { AlertTriangle, Info } from 'lucide-react';

export function DemoBanner() {
  return (
    <div className="demo-banner" role="status" aria-live="polite">
      <div className="demo-banner-content">
        <Info size={18} aria-hidden="true" />
        <div className="demo-banner-text">
          <strong>DEMO — SIMULATED DATA ONLY.</strong> Not connected to emergency services. 
          In a real emergency in India, call <strong>112</strong>.
        </div>
      </div>
    </div>
  );
}