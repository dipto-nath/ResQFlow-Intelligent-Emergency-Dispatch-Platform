import React from 'react';
import { CheckCircle2, AlertCircle, AlertTriangle, X } from 'lucide-react';

export function Toast({ id, message, type = 'success', onRemove }) {
  const icons = {
    success: <CheckCircle2 size={18} className="toast-icon text-success" />,
    error: <AlertCircle size={18} className="toast-icon text-error" />,
    warning: <AlertTriangle size={18} className="toast-icon text-warning" />
  };

  return (
    <div className={`toast toast-${type}`} role="alert">
      {icons[type] || icons.success}
      <span className="toast-message">{message}</span>
      <button
        type="button"
        className="toast-close"
        onClick={() => onRemove(id)}
        aria-label="Dismiss notification"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastContainer({ toasts = [], onRemove }) {
  if (!toasts.length) return null;

  return (
    <div className="toast-container" aria-live="polite">
      {toasts.map(toast => (
        <Toast key={toast.id} {...toast} onRemove={onRemove} />
      ))}
    </div>
  );
}
