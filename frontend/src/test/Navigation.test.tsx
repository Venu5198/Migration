import { render, screen } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Navbar } from '../components/layout/Navbar';
import { Sidebar } from '../components/layout/Sidebar';
import { AuthProvider } from '../context/AuthContext';

// Mock apiClient calls
vi.mock('../api/client', () => ({
  apiClient: {
    getHealth: vi.fn().mockResolvedValue({
      status: 'ok',
      database: 'connected',
      equus_writes: 'disabled',
    }),
    testMockTarget: vi.fn().mockResolvedValue({
      target: 'Equus Mock',
      connected: true,
      writes_allowed: false,
      safety_note: 'Writes disabled',
    }),
  },
}));

describe('Navigation and Layout Components', () => {
  it('renders Navbar with Equus safe mode badge and user subject', async () => {
    render(
      <AuthProvider>
        <MemoryRouter>
          <Navbar />
        </MemoryRouter>
      </AuthProvider>
    );

    expect(screen.getByText('Excel Migration Platform')).toBeInTheDocument();
    expect(screen.getByText(/Equus Writes: Disabled/i)).toBeInTheDocument();
    expect(screen.getByText('development')).toBeInTheDocument();
  });

  it('renders Sidebar with core lifecycle routes', () => {
    render(
      <AuthProvider>
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>
      </AuthProvider>
    );

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Topia → Equus Migration')).toBeInTheDocument();
    expect(screen.getByText('Workbooks & Sources')).toBeInTheDocument();
    expect(screen.getByText('Data Profiling')).toBeInTheDocument();
    expect(screen.getByText('Field Mapping')).toBeInTheDocument();
    expect(screen.getByText('Mapping Approvals')).toBeInTheDocument();
    expect(screen.getByText('Transformation Preview')).toBeInTheDocument();
    expect(screen.getByText('Background Jobs')).toBeInTheDocument();
    expect(screen.getByText('Reports & Reconciliation')).toBeInTheDocument();
    expect(screen.getByText('Audit Events')).toBeInTheDocument();
  });
});
