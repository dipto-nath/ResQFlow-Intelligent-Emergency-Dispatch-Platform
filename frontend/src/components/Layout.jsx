import React from 'react';
import { Outlet } from 'react-router-dom';
import { Footer } from './Footer';

export function Layout({ children }) {
  return (
    <div className="layout">
      <div className="layout-main">
        {children}
      </div>
      <Footer />
    </div>
  );
}