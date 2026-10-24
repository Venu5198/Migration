import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  Eye,
  FileCheck,
  FileSpreadsheet,
  FileText,
  Play,
  RotateCw,
  ShieldCheck,
  Table,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { Modal } from '../components/common/Modal';
import { JobResponse, MappingResponse, PreviewResult, ReconciliationReport, SourceResponse } from '../types';

export const PreviewPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialSourceId = searchParams.get('sourceId') || '';
  const initialMappingId = searchParams.get('mappingId') || '';

  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState(initialSourceId);
  const [selectedMappingId, setSelectedMappingId] = useState(initialMappingId);

  // Recent Mappings
  const [recentMappings] = useState<MappingResponse[]>(() => {
    const saved = localStorage.getItem('migration_user_mappings');
    return saved ? JSON.parse(saved) : [];
  });

  // Preview Job & Result State
  const [previewJob, setPreviewJob] = useState<JobResponse | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reconciliation Modal
  const [reconModalOpen, setReconModalOpen] = useState(false);
  const [reconciliation, setReconciliation] = useState<ReconciliationReport | null>(null);
  const [loadingRecon, setLoadingRecon] = useState(false);

  useEffect(() => {
    const loadSources = async () => {
      try {
        const res = await apiClient.listSources(1, 100);
        setSources(res.items);
        if (!selectedSourceId && res.items.length > 0) {
          setSelectedSourceId(res.items[0].source_id);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load sources.');
      }
    };
    loadSources();
  }, []);

  // Poll preview job
  useEffect(() => {
    if (!previewJob) return;
    const isTerminal = ['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'CANCELLED'].includes(
      previewJob.status
    );
    if (isTerminal) return;

    const interval = setInterval(async () => {
      try {
        const updated = await apiClient.getJob(previewJob.job_id);
        setPreviewJob(updated);
      } catch (err: any) {
        console.error('Job polling error:', err);
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [previewJob?.job_id, previewJob?.status]);

  const handleStartDryRun = async () => {
    if (!selectedSourceId || !selectedMappingId) {
      setError('Please provide both Source ID and Mapping ID.');
      return;
    }
    setIsStarting(true);
    setError(null);
    try {
      const job = await apiClient.startPreviewJob(selectedSourceId, selectedMappingId);
      setPreviewJob(job);
    } catch (err: any) {
      setError(err.message || 'Failed to start dry-run preview.');
    } finally {
      setIsStarting(false);
    }
  };

  const handleDownloadCsv = async () => {
    if (!previewJob) return;
    try {
      const blob = await apiClient.downloadReportCsv(previewJob.job_id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `migration-${previewJob.job_id}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setError(err.message || 'Failed to download CSV export.');
    }
  };

  const handleViewReconciliation = async () => {
    if (!previewJob) return;
    setLoadingRecon(true);
    try {
      const res = await apiClient.getReconciliation(previewJob.job_id);
      setReconciliation(res);
      setReconModalOpen(true);
    } catch (err: any) {
      setError(err.message || 'Failed to retrieve reconciliation data.');
    } finally {
      setLoadingRecon(false);
    }
  };

  const previewResult: PreviewResult | undefined =
    previewJob?.status === 'COMPLETED' || previewJob?.status === 'COMPLETED_WITH_ERRORS'
      ? previewJob.result
      : undefined;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Transformation Preview</h1>
        <p className="text-sm text-slate-500 mt-1">
          Perform a read-only dry-run transformation against source rows and approved field mappings. Target writes remain strictly disabled.
        </p>
      </div>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          <div className="space-y-2">
            <div>{error}</div>
            {error.toLowerCase().includes('not found') && (
              <div className="text-xs text-rose-700 bg-rose-100/60 p-2 rounded">
                <strong>Tip:</strong> The ID entered was not recognized as a field mapping. If you recently profiled this workbook, make sure to define a mapping in <strong>Field Mapping</strong> and approve it in <strong>Mapping Approvals</strong> first.
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => navigate('/mappings')}>
                    Go to Field Mapping &rarr;
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => navigate('/approvals')}>
                    Go to Mapping Approvals &rarr;
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Alert>
      )}

      {/* Form Trigger Card */}
      <Card
        title="Execute Transformation Dry-Run"
        subtitle="Select a source workbook and an approved field mapping. Writes remain strictly isolated."
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Source Workbook
              </label>
              <select
                value={selectedSourceId}
                onChange={(e) => {
                  const newSourceId = e.target.value;
                  setSelectedSourceId(newSourceId);
                  const validForNewSource = recentMappings.filter((m) => m.source_id === newSourceId);
                  if (validForNewSource.length > 0 && !validForNewSource.some((m) => m.mapping_id === selectedMappingId)) {
                    setSelectedMappingId(validForNewSource[0].mapping_id);
                  } else if (validForNewSource.length === 0) {
                    setSelectedMappingId('');
                  }
                }}
                className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white"
              >
                {sources.map((s) => (
                  <option key={s.source_id} value={s.source_id}>
                    {s.original_filename} ({s.source_id.substring(0, 8)}...)
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Approved Mapping ID
              </label>
              <input
                type="text"
                value={selectedMappingId}
                onChange={(e) => setSelectedMappingId(e.target.value)}
                placeholder="Paste approved Mapping UUID (from Field Mapping & Approvals)"
                className="w-full text-sm font-mono px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">
                Requires an Approved Mapping UUID (do not use Profiling Job UUID).
              </span>
            </div>
          </div>

          {recentMappings.length > 0 && (
            <div className="pt-2">
              <span className="text-xs text-slate-500 block mb-1.5 font-medium">
                Quick Select from Mappings for Selected Workbook:
              </span>
              <div className="flex flex-wrap gap-2">
                {recentMappings
                  .filter((m) => !selectedSourceId || m.source_id === selectedSourceId)
                  .map((m) => (
                    <button
                      key={m.mapping_id}
                      onClick={() => {
                        setSelectedSourceId(m.source_id);
                        setSelectedMappingId(m.mapping_id);
                      }}
                      className={`text-xs px-2.5 py-1 rounded border flex items-center gap-1.5 transition-colors ${
                        selectedMappingId === m.mapping_id
                          ? 'bg-blue-800 text-white border-blue-900 font-semibold'
                          : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      <span>{m.source_field} &rarr; {m.target_field}</span>
                      <Badge variant={m.status === 'approved' ? 'success' : 'warning'}>
                        {m.status}
                      </Badge>
                    </button>
                  ))}
                {recentMappings.filter((m) => !selectedSourceId || m.source_id === selectedSourceId).length === 0 && (
                  <span className="text-xs text-slate-400 italic">No saved mappings found for this workbook.</span>
                )}
              </div>
            </div>
          )}

          <div className="flex justify-end pt-2">
            <Button
              variant="primary"
              disabled={!selectedSourceId || !selectedMappingId || isStarting}
              isLoading={isStarting}
              onClick={handleStartDryRun}
              icon={<Play className="w-4 h-4" />}
            >
              Start Dry-Run Preview (202 Accepted)
            </Button>
          </div>
        </div>
      </Card>

      {/* Active Preview Job Card */}
      {previewJob && (
        <Card
          title={
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-slate-500">Preview Job: {previewJob.job_id}</span>
              <Badge
                variant={
                  previewJob.status === 'COMPLETED'
                    ? 'success'
                    : previewJob.status === 'COMPLETED_WITH_ERRORS'
                    ? 'warning'
                    : previewJob.status === 'FAILED'
                    ? 'danger'
                    : 'info'
                }
              >
                {previewJob.status}
              </Badge>
            </div>
          }
          action={
            previewResult && (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleViewReconciliation}
                  isLoading={loadingRecon}
                  icon={<FileCheck className="w-3.5 h-3.5" />}
                >
                  Reconciliation
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={handleDownloadCsv}
                  icon={<Download className="w-3.5 h-3.5" />}
                >
                  Export Safe CSV
                </Button>
              </div>
            )
          }
        >
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
            <div>
              <span className="text-slate-400 block font-medium">Target Connector Mode</span>
              <span className="font-semibold text-rose-700">Writes Disabled (Dry Run)</span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">Worker Progress</span>
              <span className="font-semibold text-slate-800">{previewJob.progress}%</span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">Claim Attempts</span>
              <span className="font-semibold text-slate-800">{previewJob.attempts}</span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">Status</span>
              <span className="font-semibold text-slate-800">{previewJob.status}</span>
            </div>
          </div>
        </Card>
      )}

      {/* Preview Results Table */}
      {previewResult && (
        <div className="space-y-6">
          {/* KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            <Card className="border-l-4 border-l-blue-800">
              <span className="text-xs font-semibold text-slate-500 uppercase">Source Data Records</span>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {previewResult.records_evaluated ?? previewResult.evaluated_rows ?? 0}
              </div>
              <span className="text-[10px] text-slate-400 mt-0.5 block">Employee data rows</span>
            </Card>

            <Card className="border-l-4 border-l-indigo-600">
              <span className="text-xs font-semibold text-slate-500 uppercase">Header Rows (Excluded)</span>
              <div className="text-2xl font-bold text-indigo-700 mt-1">
                {previewResult.header_rows_count ?? 1}
              </div>
              <span className="text-[10px] text-slate-400 mt-0.5 block">Metadata / rules excluded</span>
            </Card>

            <Card className="border-l-4 border-l-emerald-600">
              <span className="text-xs font-semibold text-slate-500 uppercase">Eligible / Proposed</span>
              <div className="text-2xl font-bold text-emerald-700 mt-1">
                {previewResult.eligible_records ?? previewResult.migrated_rows ?? 0}
              </div>
              <span className="text-[10px] text-slate-400 mt-0.5 block">Transformed records</span>
            </Card>

            <Card className="border-l-4 border-l-amber-500">
              <span className="text-xs font-semibold text-slate-500 uppercase">Structural Empty Rows</span>
              <div className="text-2xl font-bold text-amber-700 mt-1">
                {previewResult.structural_empty_rows ?? 0}
              </div>
              <span className="text-[10px] text-slate-400 mt-0.5 block">Blank rows skipped</span>
            </Card>

            <Card className="border-l-4 border-l-purple-600">
              <span className="text-xs font-semibold text-slate-500 uppercase">CSV Injection Guard</span>
              <div className="text-sm font-semibold text-purple-800 mt-2 flex items-center gap-1">
                <ShieldCheck className="w-4 h-4 text-purple-700" /> Active (Escaped)
              </div>
              <span className="text-[10px] text-slate-400 mt-0.5 block">Formulas sanitised</span>
            </Card>
          </div>

          {/* Row-Level Preview */}
          <Card
            title="Transformed Record Previews"
            subtitle="Comparing extracted source values against evaluated target schemas"
          >
            {((!previewResult.records || previewResult.records.length === 0) &&
              (!previewResult.preview_rows || previewResult.preview_rows.length === 0)) ? (
              <div className="py-8 text-center text-xs text-slate-500">
                No preview records returned from workbook.
              </div>
            ) : (
              <div className="overflow-x-auto max-h-96 overflow-y-auto border border-slate-200 rounded-md">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200 sticky top-0">
                    <tr>
                      <th className="py-2.5 px-3">Location</th>
                      <th className="py-2.5 px-3">Target Entity</th>
                      <th className="py-2.5 px-3">Proposed Field Values</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono">
                    {(previewResult.records || previewResult.preview_rows || []).map((row: any, idx: number) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 text-slate-500 whitespace-nowrap">
                          {row.sheet ? `${row.sheet} : Row ${row.row}` : `#${row.row_number || idx + 1}`}
                        </td>
                        <td className="py-2.5 px-3 text-slate-700 font-semibold whitespace-nowrap">
                          {row.target_entity || 'Target'}
                        </td>
                        <td className="py-2.5 px-3 font-semibold text-blue-900">
                          {JSON.stringify(row.proposed || row.target || {})}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Warnings & Issues */}
          {((previewResult.warnings && previewResult.warnings.length > 0) ||
            (previewResult.issues && previewResult.issues.length > 0)) && (
            <Card title="Dry-Run Findings & Warnings">
              <div className="space-y-2">
                {previewResult.warnings?.map((w, idx) => (
                  <div key={idx} className="p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900 flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                    <span>{typeof w === 'string' ? w : JSON.stringify(w)}</span>
                  </div>
                ))}
                {previewResult.issues?.map((iss, idx) => (
                  <div key={idx} className="p-3 bg-rose-50 border border-rose-200 rounded text-xs text-rose-900 flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                    <span>{typeof iss === 'string' ? iss : JSON.stringify(iss)}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Reconciliation Modal */}
      <Modal
        isOpen={reconModalOpen}
        onClose={() => setReconModalOpen(false)}
        title="Reconciliation Audit Summary"
      >
        {reconciliation && (
          <div className="space-y-4 text-xs">
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded flex items-center justify-between text-emerald-900 font-semibold">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-700" />
                <span>Target Writes: Strictly Disabled (Dry Run Reconciliation)</span>
              </div>
              <Badge variant="success">Audited</Badge>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                <span className="text-slate-500 block text-[11px]">Source Records Evaluated</span>
                <span className="text-lg font-bold text-slate-800">{reconciliation.source_records ?? 0}</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                <span className="text-slate-500 block text-[11px]">Accepted / Proposed Records</span>
                <span className="text-lg font-bold text-emerald-700">{reconciliation.accepted_records ?? 0}</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                <span className="text-slate-500 block text-[11px]">Rejected Records</span>
                <span className="text-lg font-bold text-rose-700">{reconciliation.rejected_records ?? 0}</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                <span className="text-slate-500 block text-[11px]">Target Reconciliation Mode</span>
                <span className="text-xs font-bold text-slate-700">{reconciliation.target_reconciliation || 'NOT_PERFORMED'}</span>
              </div>
            </div>

            {reconciliation.summary && (
              <div>
                <span className="font-semibold text-slate-700 block mb-1">Reconciliation Summary:</span>
                <pre className="p-3 bg-slate-50 border border-slate-200 rounded font-mono text-slate-800 overflow-x-auto">
                  {JSON.stringify(reconciliation.summary, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};
