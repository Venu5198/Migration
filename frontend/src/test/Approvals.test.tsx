import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '../api/client';
import { AuthProvider } from '../context/AuthContext';
import { ApprovalsPage } from '../pages/ApprovalsPage';

vi.mock('../api/client', () => ({
  apiClient: {
    getMapping: vi.fn(),
    approveMapping: vi.fn(),
  },
}));

describe('ApprovalsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('detects unresolved mapping and warns that it cannot be approved', async () => {
    vi.mocked(apiClient.getMapping).mockResolvedValue({
      mapping_id: 'map-unresolved-1',
      source_id: 'src-1',
      source_entity: 'Employee',
      source_sheet: 'Sheet1',
      source_field: 'UnknownCol',
      target_entity: 'Employee',
      target_field: 'unmapped',
      mapping_type: 'unresolved',
      status: 'proposed',
      version: 1,
      required: false,
      created_at: new Date().toISOString(),
      created_by: 'creator_1',
    });

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/approvals?mappingId=map-unresolved-1']}>
          <ApprovalsPage />
        </MemoryRouter>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/Unresolved mappings cannot be approved per contract/i)).toBeInTheDocument();
      const approveBtn = screen.getByRole('button', { name: /Approve Mapping/i });
      expect(approveBtn).toBeDisabled();
    });
  });

  it('detects self-review when creator matches active session actor', async () => {
    vi.mocked(apiClient.getMapping).mockResolvedValue({
      mapping_id: 'map-self-1',
      source_id: 'src-1',
      source_entity: 'Employee',
      source_sheet: 'Sheet1',
      source_field: 'EmployeeID',
      target_entity: 'Employee',
      target_field: 'employee_id',
      mapping_type: 'direct',
      status: 'proposed',
      version: 1,
      required: true,
      created_at: new Date().toISOString(),
      created_by: 'development',
    });

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/approvals?mappingId=map-self-1']}>
          <ApprovalsPage />
        </MemoryRouter>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/Self-Review Detected/i)).toBeInTheDocument();
      expect(screen.getByText(/Separation of Duties/i)).toBeInTheDocument();
    });
  });
});
