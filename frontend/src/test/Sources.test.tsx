import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '../api/client';
import { AuthProvider } from '../context/AuthContext';
import { SourcesPage } from '../pages/SourcesPage';

vi.mock('../api/client', () => ({
  apiClient: {
    listSources: vi.fn(),
    uploadSource: vi.fn(),
  },
}));

describe('SourcesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders upload interface and loads workbook inventory', async () => {
    vi.mocked(apiClient.listSources).mockResolvedValue({
      items: [
        {
          source_id: 'src-12345678',
          original_filename: 'synthetic_employees.xlsx',
          sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
          created_at: new Date().toISOString(),
          sheets: [
            {
              name: 'Employees',
              max_row: 10,
              max_column: 4,
              headers: ['emp_id', 'first_name', 'last_name', 'country'],
              inferred_types: { emp_id: 'string', country: 'string' },
              issues: [],
            },
          ],
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    render(
      <AuthProvider>
        <MemoryRouter>
          <SourcesPage />
        </MemoryRouter>
      </AuthProvider>
    );

    expect(screen.getByText('Source Workbooks')).toBeInTheDocument();
    expect(screen.getByText('Upload Excel Workbook')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('synthetic_employees.xlsx')).toBeInTheDocument();
      expect(screen.getByText('Inspect Schema')).toBeInTheDocument();
    });
  });

  it('rejects non-excel files with an error message', async () => {
    vi.mocked(apiClient.listSources).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });

    const { container } = render(
      <AuthProvider>
        <MemoryRouter>
          <SourcesPage />
        </MemoryRouter>
      </AuthProvider>
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeInTheDocument();

    const invalidFile = new File(['dummy content'], 'document.pdf', { type: 'application/pdf' });

    fireEvent.change(input, { target: { files: [invalidFile] } });

    await waitFor(() => {
      expect(screen.getByText(/Only Excel workbooks \(\.xlsx, \.xlsm\) are supported/i)).toBeInTheDocument();
    });
  });
});
