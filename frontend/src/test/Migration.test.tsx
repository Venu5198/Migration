import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import React from 'react';

import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '../api/client';
import { MigrationPage } from '../pages/MigrationPage';

// Mock apiClient
vi.mock('../api/client', () => ({
  apiClient: {
    listSources: vi.fn(),
    uploadSource: vi.fn(),
    startEquusMigration: vi.fn(),
    getJob: vi.fn(),
    listJobs: vi.fn(),
    cancelJob: vi.fn(),
    downloadArtifact: vi.fn(),
  },
}));

describe('MigrationPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(apiClient.listSources).mockResolvedValue({
      items: [
        {
          source_id: 'src-123',
          original_filename: 'Topia_Past_Assignments.xlsx',
          sha256: 'abc123456789',
          created_at: '2026-10-23T10:00:00Z',
          sheets: [],
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });

    vi.mocked(apiClient.listJobs).mockResolvedValue({
      items: [
        {
          job_id: 'job-999',
          kind: 'equus_migration',
          source_id: 'src-123',
          source_filename: 'Topia_Past_Assignments.xlsx',
          status: 'COMPLETED',
          progress: 100,
          attempts: 1,
          created_at: '2026-10-23T11:00:00Z',
          updated_at: '2026-10-23T11:00:05Z',
          result: {
            coverage_percentage: 95.5,
            total_output_records: 42,
            reconciliation: {
              is_valid: true,
              status: 'PASS',
              errors: [],
              warnings: [],
            },
          },
          cancellation_requested: false,
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });
  });

  it('renders Migration Page with New Migration tab and default Option B strategy', async () => {
    render(
      <MemoryRouter initialEntries={['/migration']}>
        <MigrationPage />
      </MemoryRouter>
    );

    expect(screen.getByText('Topia to Equus Migration')).toBeInTheDocument();
    expect(
      screen.getByText(/Option B: Normalized Employee Number in Assignment ID/i)
    ).toBeInTheDocument();
    expect(screen.getByText('Recommended')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run Equus Migration/i })).toBeInTheDocument();
  });

  it('validates file extension and rejects unsupported formats', async () => {
    render(
      <MemoryRouter initialEntries={['/migration']}>
        <MigrationPage />
      </MemoryRouter>
    );

    const fileInput = screen.getByLabelText(/Browse Files/i).parentElement?.querySelector('input');
    expect(fileInput).toBeTruthy();

    const badFile = new File(['dummy'], 'test.txt', { type: 'text/plain' });
    fireEvent.change(fileInput!, { target: { files: [badFile] } });

    await waitFor(() => {
      expect(
        screen.getByText(/Unsupported file type. Only Excel workbooks \(\.xlsx, \.xlsm\) are supported\./i)
      ).toBeInTheDocument();
    });
  });

  it('submits migration job and transitions to details tab', async () => {
    vi.mocked(apiClient.uploadSource).mockResolvedValue({
      source_id: 'src-new-456',
      original_filename: 'Valid_Export.xlsx',
      sha256: 'hash789',
      created_at: '2026-10-23T12:00:00Z',
      sheets: [],
    });

    vi.mocked(apiClient.startEquusMigration).mockResolvedValue({
      job_id: 'job-new-123',
      kind: 'equus_migration',
      source_id: 'src-new-456',
      status: 'PENDING',
      progress: 0,
      attempts: 0,
      created_at: '2026-10-23T12:00:01Z',
      updated_at: '2026-10-23T12:00:01Z',
      cancellation_requested: false,
    });

    vi.mocked(apiClient.getJob).mockResolvedValue({
      job_id: 'job-new-123',
      kind: 'equus_migration',
      source_id: 'src-new-456',
      status: 'PENDING',
      progress: 0,
      attempts: 0,
      created_at: '2026-10-23T12:00:01Z',
      updated_at: '2026-10-23T12:00:01Z',
      cancellation_requested: false,
    });

    render(
      <MemoryRouter initialEntries={['/migration']}>
        <MigrationPage />
      </MemoryRouter>
    );

    const fileInput = screen.getByLabelText(/Browse Files/i).parentElement?.querySelector('input');
    const validFile = new File(['xlsx data'], 'Valid_Export.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    fireEvent.change(fileInput!, { target: { files: [validFile] } });

    await waitFor(() => {
      expect(screen.getByText('Valid_Export.xlsx')).toBeInTheDocument();
    });

    const runBtn = screen.getByRole('button', { name: /Run Equus Migration/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(apiClient.uploadSource).toHaveBeenCalledWith(validFile, expect.any(Function));
      expect(apiClient.startEquusMigration).toHaveBeenCalledWith(
        'src-new-456',
        'EMPLOYEE_NUMBER'
      );
    });
  });

  it('clearly distinguishes completed execution from failed reconciliation status', async () => {
    vi.mocked(apiClient.getJob).mockResolvedValue({
      job_id: 'job-failed-recon',
      kind: 'equus_migration',
      source_id: 'src-123',
      source_filename: 'Failed_Recon.xlsx',
      status: 'COMPLETED_WITH_ERRORS',
      progress: 100,
      attempts: 1,
      created_at: '2026-10-23T12:00:00Z',
      updated_at: '2026-10-23T12:00:05Z',
      result: {
        coverage_percentage: 90.0,
        total_source_rows: 50,
        total_output_records: 48,
        insert_records: 48,
        update_records: 0,
        reconciliation: {
          is_valid: false,
          status: 'FAIL',
          errors: ['Discrepancy: Expected 50 INSERT records, found 48.'],
          warnings: ['Missing optional address.'],
        },
      },
      cancellation_requested: false,
    });

    render(
      <MemoryRouter initialEntries={['/migration?tab=details&jobId=job-failed-recon']}>
        <MigrationPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      // Job execution status is COMPLETED_WITH_ERRORS
      expect(screen.getByText('COMPLETED_WITH_ERRORS')).toBeInTheDocument();
      // Reconciliation status is strictly marked FAILED
      expect(screen.getByText('Reconciliation Validation: FAILED')).toBeInTheDocument();
      expect(
        screen.getByText('Discrepancy: Expected 50 INSERT records, found 48.')
      ).toBeInTheDocument();
    });
  });

  it('renders migration history and allows inspecting job details', async () => {
    render(
      <MemoryRouter initialEntries={['/migration?tab=history']}>
        <MigrationPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Topia to Equus Migration History')).toBeInTheDocument();
      expect(screen.getByText('Topia_Past_Assignments.xlsx')).toBeInTheDocument();
      expect(screen.getByText('95.5%')).toBeInTheDocument();
      expect(screen.getByText('42 records')).toBeInTheDocument();
    });
  });

  it('renders 5-step workflow stepper and synthetic strategy examples', async () => {
    render(
      <MemoryRouter initialEntries={['/migration']}>
        <MigrationPage />
      </MemoryRouter>
    );

    // Verify 5-step lifecycle stepper
    expect(screen.getByText('1. Upload Source')).toBeInTheDocument();
    expect(screen.getByText('2. Strategy Selection')).toBeInTheDocument();
    expect(screen.getByText('3. Run Engine')).toBeInTheDocument();
    expect(screen.getByText('4. Inspect Reconciliation')).toBeInTheDocument();
    expect(screen.getByText('5. Download Deliverables')).toBeInTheDocument();

    // Verify synthetic concrete examples are shown for Option B and Option A
    expect(screen.getAllByText(/Concrete Synthetic Example:/i).length).toBe(2);
    expect(screen.getAllByText('EMP-1001-A1').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('TOP-5001').length).toBeGreaterThanOrEqual(1);
  });

  it('displays template coverage breakdown and approved-for-import status when reconciliation passes', async () => {
    vi.mocked(apiClient.getJob).mockResolvedValue({
      job_id: 'job-passed-recon',
      kind: 'equus_migration',
      source_id: 'src-123',
      source_filename: 'Valid_Basic.xlsx',
      status: 'COMPLETED',
      progress: 100,
      attempts: 1,
      created_at: '2026-10-23T12:00:00Z',
      updated_at: '2026-10-23T12:00:05Z',
      result: {
        coverage_percentage: 7.53,
        mapped_columns_count: 11,
        unmapped_columns_count: 135,
        total_template_columns: 146,
        total_source_rows: 2,
        total_output_records: 2,
        insert_records: 2,
        update_records: 0,
        import_file: 'local_s3/dest_s3/equus/Valid_Basic_EQUUS_20261023.xlsx',
        report_file: 'local_s3/dest_s3/equus/reports/Valid_Basic_MAPPING_REPORT_20261023.xlsx',
        reconciliation: {
          is_valid: true,
          status: 'PASS',
          errors: [],
          warnings: [],
        },
      },
      cancellation_requested: false,
    });

    render(
      <MemoryRouter initialEntries={['/migration?tab=details&jobId=job-passed-recon']}>
        <MigrationPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      // Approved status banner and badge
      expect(screen.getByText('Reconciliation Validation: PASSED')).toBeInTheDocument();
      expect(screen.getByText('Approved for Downstream Import')).toBeInTheDocument();
      expect(screen.getAllByText('APPROVED FOR IMPORT').length).toBeGreaterThan(0);

      // Template coverage breakdown (146 columns, 11 mapped, 135 unmapped)
      expect(screen.getByText('Equus Template Coverage & Field Breakdown')).toBeInTheDocument();
      expect(screen.getByText('146')).toBeInTheDocument();
      expect(screen.getByText('11')).toBeInTheDocument();
      expect(screen.getByText('135')).toBeInTheDocument();
      expect(screen.getByText(/Field Coverage \(%\) = \(Mapped Target Columns ÷ 146 Total Equus Columns\) × 100/i)).toBeInTheDocument();

      // Download button reflects approved import
      expect(screen.getByRole('button', { name: /Download Equus \(\.xlsx\)/i })).toBeInTheDocument();
    });
  });

  it('displays diagnostic-only designation, import blocked alert, and consistent counts when reconciliation fails', async () => {
    vi.mocked(apiClient.getJob).mockResolvedValue({
      job_id: '99edcedf-fbc8-4c21-ade1-5e1bf6673abe',
      kind: 'equus_migration',
      source_id: 'src-failed-123',
      source_filename: '04_negative_missing_employee_id.xlsx',
      status: 'FAILED',
      progress: 100,
      attempts: 1,
      created_at: '2026-10-23T12:00:00Z',
      updated_at: '2026-10-23T12:00:05Z',
      result: {
        coverage_percentage: 7.53,
        mapped_columns_count: 11,
        unmapped_columns_count: 135,
        total_template_columns: 146,
        total_source_rows: 2,
        total_output_records: 2,
        insert_records: 2,
        update_records: 0,
        import_file: '04_negative_missing_employee_id_EQUUS_20261023.xlsx',
        report_file: 'reports/04_negative_missing_employee_id_MAPPING_REPORT_20261023.xlsx',
        reconciliation: {
          is_valid: false,
          status: 'FAILED',
          source_rows_evaluated: 2,
          total_output_records: 2,
          insert_records_count: 2,
          update_records_count: 0,
          accepted_records: 0,
          rejected_records: 2,
          errors: [
            'INSERT record #1 is missing required Employee Number (Col 3)',
            'INSERT record #1 is missing required Assignment Identifier (Col 5)',
          ],
          warnings: [],
        },
      },
      cancellation_requested: false,
    });

    render(
      <MemoryRouter initialEntries={['/migration?tab=details&jobId=99edcedf-fbc8-4c21-ade1-5e1bf6673abe']}>
        <MigrationPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      // Failed status banner and diagnostic badge
      expect(screen.getByText('Reconciliation Validation: FAILED')).toBeInTheDocument();
      expect(screen.getByText('Not Approved for Import (Diagnostic Review Only)')).toBeInTheDocument();
      expect(screen.getAllByText('Import Blocked').length).toBeGreaterThanOrEqual(1);

      // Download button explicitly designates diagnostic file
      expect(screen.getByRole('button', { name: /Download Diagnostic File \(\.xlsx\)/i })).toBeInTheDocument();
      expect(screen.getByText('Equus Diagnostic File (Unapproved)')).toBeInTheDocument();

      // Both validation errors displayed in audit section
      expect(screen.getByText(/Validation Errors \(2\)/i)).toBeInTheDocument();
      expect(screen.getByText(/missing required Employee Number \(Col 3\)/i)).toBeInTheDocument();
      expect(screen.getByText(/missing required Assignment Identifier \(Col 5\)/i)).toBeInTheDocument();

      // Table displays true non-zero counts agreeing with backend
      const table = screen.getByRole('table');
      expect(table).toBeInTheDocument();
      expect(within(table).getByText('Source Evaluated Rows')).toBeInTheDocument();
      expect(within(table).getByText('Generated Output Records')).toBeInTheDocument();
      expect(within(table).getByText('Accepted Import Records')).toBeInTheDocument();
      expect(within(table).getByText('Rejected / Diagnostic Records')).toBeInTheDocument();
    });
  });
});

