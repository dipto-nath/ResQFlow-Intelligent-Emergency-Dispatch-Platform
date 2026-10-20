import React from 'react';
import { Info } from 'lucide-react';

export function Footer() {
  return (
    <footer className="footer" role="contentinfo">
      <div className="footer-content">
        <div className="footer-disclaimer">
          <Info size={14} aria-hidden="true" />
          <span>DEMO — SIMULATED DATA ONLY. Not connected to emergency services. In a real emergency in India, call <strong>112</strong>.</span>
        </div>
        <div className="footer-meta">
          <span>Sahayak Dispatch v1.0.0-prototype</span>
          <span>Prototype priority score — not clinically validated; dispatcher review required.</span>
        </div>
      </div>
    </footer>
  );
}