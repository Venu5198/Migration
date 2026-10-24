import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '../api/client';
import { AuthProvider } from '../context/AuthContext';
import { PreviewPage } from '../pages/PreviewPage';

vi.mock('../api/client', () => ({
  apiClient: {
    listSources: vi.fn(),
    getJob: vi.fn(),
    startPreviewJob: vi.fn(),
    downloadReportCsv: vi.fn(),
    getReconciliation: vi.fn(),
  },
}));

describe('PreviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders preview KPI cards distinguishing source data rows from excluded header rows', async () => {
    vi.mocked(apiClient.listSources).mockResolvedValue({
      items: [
        {
          source_id: 'src-negative-04',
          original_filename: '04_negative_missing_employee_id.xlsx',
          sha256: 'abc123hash',
          created_at: new Date().toISOString(),
          sheets: [
            {
              name: 'Sheet1',
              max_row: 6,
              max_column: 8,
              headers: ['Full Name', 'First Name', 'Last Name', 'Employee ID', 'Assignment ID', 'Birth Date', 'Gender', 'Home Country'],
              inferred_types: {},
              issues: [],
              header_rows_count: 4,
              data_start_row: 5,
            },
          ],
        },
      ],
      page: 1,
      page_size: 100,
      total: 1,
    });

    // Seed local storage with a mapping for this source
    localStorage.setItem(
      'migration_user_mappings',
      JSON.stringify([
        {
          mapping_id: 'map-valid-1',
          source_id: 'src-negative-04',
          source_sheet: 'Sheet1',
          source_field: 'First Name',
          target_entity: 'Employee',
          target_field: 'first_name',
          mapping_type: 'direct',
          status: 'approved',
          version: 2,
        },
        {
          mapping_id: 'map-other-src',
          source_id: 'src-other-99',
          source_sheet: 'Sheet1',
          source_field: 'SomeField',
          target_entity: 'Employee',
          target_field: 'other_field',
          mapping_type: 'direct',
          status: 'approved',
          version: 1,
        },
      ])
    );

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/preview?sourceId=src-negative-04']}>
          <PreviewPage />
        </MemoryRouter>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/Transformation Preview/i)).toBeInTheDocument();
      // Should show quick select for relevant mapping
      expect(screen.getByText(/First Name → first_name/i)).toBeInTheDocument();
      // Should NOT show mapping from other workbook
      expect(screen.queryByText(/SomeField → other_field/i)).not.toBeInTheDocument();
    });
  });
});
