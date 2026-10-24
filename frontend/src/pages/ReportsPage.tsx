import React, { useState } from 'react';
import {
  CheckCircle2,
  Download,
  FileCheck,
  FileSpreadsheet,
  FileText,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { ReconciliationReport } from '../types';

export const ReportsPage: React.FC = () => {
  const [jobId, setJobId] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [reconciliation, setReconciliation] = useState<ReconciliationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleFetchReport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!jobId.trim()) return;

    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await apiClient.getReconciliation(jobId.trim());
      setReconciliation(res);
      setSuccess('Reconciliation metrics loaded successfully.');
    } catch (err: any) {
      setError(err.message || 'Report was not found for this Job ID.');
      setReconciliation(null);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadCsv = async () => {
    if (!jobId.trim()) return;
    setExporting(true);
    setError(null);
    try {
      const blob = await apiClient.downloadReportCsv(jobId.trim());
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `migration-${jobId.trim()}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      setSuccess('CSV report downloaded and audit lineage recorded.');
    } catch (err: any) {
      setError(err.message || 'Failed to download report export.');
    } finally {
      setExporting(false);
    }
  };

  const handleDownloadArtifact = async (artifact: 'report' | 'import') => {
    if (!jobId.trim()) return;
    setExporting(true);
    setError(null);
    try {
      const { blob, filename } = await apiClient.downloadArtifact(jobId.trim(), artifact);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      setSuccess(`Exported ${filename} successfully.`);
    } catch (err: any) {
      setError(err.message || 'Failed to download artifact.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Reports & Reconciliation</h1>
        <p className="text-sm text-slate-500 mt-1">
          Export safe CSV reports and verify row-level reconciliation metrics. Downloads record tamper-evident audit lineage events.
        </p>
      </div>

      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}
      {success && <Alert type="success" onClose={() => setSuccess(null)}>{success}</Alert>}

      {/* Safety Notice */}
      <Alert type="info" title="Formula Injection Protection Active">
        Every exported CSV cell value beginning with =, +, -, @, tab, carriage return, pipe (|), or percent (%) is automatically escaped with a leading apostrophe to prevent spreadsheet formula injection attacks.
      </Alert>

      {/* Report Query Form */}
      <Card title="Query Job Report & Reconciliation Data">
        <form onSubmit={handleFetchReport} className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <input
              type="text"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              placeholder="Enter Preview Job UUID (e.g. 550e8400-e29b-...)"
              className="w-full text-sm font-mono px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
              required
            />
          </div>
          <Button
            type="submit"
            variant="primary"
            isLoading={loading}
            icon={<Search className="w-4 h-4" />}
          >
            Load Reconciliation
          </Button>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={!jobId.trim() || exporting}
              isLoading={exporting}
              onClick={handleDownloadCsv}
              icon={<Download className="w-4 h-4" />}
            >
              CSV Preview
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!jobId.trim() || exporting}
              onClick={() => handleDownloadArtifact('import')}
              icon={<Download className="w-4 h-4" />}
            >
              Equus Migration (.xlsx)
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!jobId.trim() || exporting}
              onClick={() => handleDownloadArtifact('report')}
              icon={<Download className="w-4 h-4" />}
            >
              Migration Results (.xlsx)
            </Button>
          </div>
        </form>
      </Card>

      {/* Reconciliation Summary Card */}
      {reconciliation && (
        <Card
          title={
            <div className="flex items-center gap-2">
              <FileCheck className="w-5 h-5 text-emerald-700" />
              <span>Target Writes: Strictly Disabled (Dry Run Audit)</span>
              <Badge variant="success">Lineage Recorded</Badge>
            </div>
          }
          subtitle={`Verified for Job ID: ${jobId}`}
        >
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
              <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                <span className="text-slate-500 block text-[11px]">Source Records</span>
                <span className="text-xl font-bold text-slate-900">{reconciliation.source_records ?? 0}</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                <span className="text-slate-500 block text-[11px]">Accepted Records</span>
                <span className="text-xl font-bold text-emerald-700">{reconciliation.accepted_records ?? 0}</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                <span className="text-slate-500 block text-[11px]">Rejected Records</span>
                <span className="text-xl font-bold text-rose-700">{reconciliation.rejected_records ?? 0}</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                <span className="text-slate-500 block text-[11px]">Target Status</span>
                <span className="text-xs font-bold text-slate-700">{reconciliation.target_reconciliation || 'NOT_PERFORMED'}</span>
              </div>
            </div>

            {reconciliation.summary && (
              <div>
                <h4 className="text-xs font-semibold text-slate-700 uppercase mb-2">
                  Reconciliation Summary
                </h4>
                <div className="bg-slate-50 border border-slate-200 rounded-md p-4">
                  <pre className="font-mono text-xs text-slate-800 overflow-x-auto">
                    {JSON.stringify(reconciliation.summary, null, 2)}
                  </pre>
                </div>
              </div>
            )}

            {reconciliation.details && (
              <div>
                <h4 className="text-xs font-semibold text-slate-700 uppercase mb-2">
                  Detailed Field Breakdown
                </h4>
                <div className="bg-slate-50 border border-slate-200 rounded-md p-4">
                  <pre className="font-mono text-xs text-slate-800 overflow-x-auto">
                    {JSON.stringify(reconciliation.details, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  );
};
