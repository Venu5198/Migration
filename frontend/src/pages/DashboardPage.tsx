import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle,
  Clock,
  Database,
  FileSpreadsheet,
  GitBranch,
  PlayCircle,
  ShieldAlert,
  ShieldCheck,
  Upload,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { HealthResponse, SourceResponse } from '../types';

export const DashboardPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [totalSources, setTotalSources] = useState(0);

  useEffect(() => {
    const loadDashboardData = async () => {
      setLoading(true);
      try {
        const [healthRes, sourcesRes] = await Promise.all([
          apiClient.getHealth().catch(() => null),
          apiClient.listSources(1, 10).catch(() => ({ items: [], total: 0, page: 1, page_size: 10 })),
        ]);
        if (healthRes) setHealth(healthRes);
        setSources(sourcesRes.items);
        setTotalSources(sourcesRes.total);
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  // Compute aggregated quality findings from real loaded sources
  const totalSheets = sources.reduce((acc, s) => acc + (s.sheets?.length || 0), 0);
  const totalIssues = sources.reduce(
    (acc, s) => acc + (s.sheets || []).reduce((shAcc, sh) => shAcc + (sh.issues?.length || 0), 0),
    0
  );
  const totalDuplicateRows = sources.reduce(
    (acc, s) =>
      acc +
      (s.sheets || []).reduce(
        (shAcc, sh) =>
          shAcc + (sh.issues || []).filter((i) => i.code === 'DUPLICATE_ROW').length,
        0
      ),
    0
  );

  return (
    <div className="space-y-6">
      {/* Top Welcome & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Migration Overview</h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time status of Excel source inventories, profiling jobs, and approved field mappings.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/sources">
            <Button variant="primary" icon={<Upload className="w-4 h-4" />}>
              Upload Workbook
            </Button>
          </Link>
          <Link to="/mappings">
            <Button variant="outline" icon={<GitBranch className="w-4 h-4" />}>
              Create Mapping
            </Button>
          </Link>
        </div>
      </div>

      {/* Security Banner */}
      <Alert type="warning" title="Equus Target Writes Strictly Disabled">
        All migration previews and transformations execute in dry-run mode against isolated synthetic memory and MongoDB repositories. Target API connectors raise a strict PermissionError by contract.
      </Alert>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-blue-800">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Workbooks Inventoried
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {loading ? '...' : totalSources}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {totalSheets} sheets detected
              </div>
            </div>
            <div className="p-3 bg-blue-50 text-blue-800 rounded-lg">
              <FileSpreadsheet className="w-6 h-6" />
            </div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-emerald-600">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Database Status
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1 capitalize">
                {health?.database === 'connected' ? 'Connected' : 'Degraded'}
              </div>
              <div className="text-xs text-emerald-600 mt-1 font-medium">
                MongoDB 7 Storage Engine
              </div>
            </div>
            <div className="p-3 bg-emerald-50 text-emerald-700 rounded-lg">
              <Database className="w-6 h-6" />
            </div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-amber-500">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Schema Findings
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {loading ? '...' : totalIssues}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {totalDuplicateRows} duplicate row issues
              </div>
            </div>
            <div className="p-3 bg-amber-50 text-amber-700 rounded-lg">
              <AlertTriangle className="w-6 h-6" />
            </div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-purple-600">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Safety Boundary
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                Isolated
              </div>
              <div className="text-xs text-purple-700 mt-1 font-medium">
                Read-only dry runs
              </div>
            </div>
            <div className="p-3 bg-purple-50 text-purple-700 rounded-lg">
              <ShieldCheck className="w-6 h-6" />
            </div>
          </div>
        </Card>
      </div>

      {/* Two Column Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Workbooks List */}
        <div className="lg:col-span-2">
          <Card
            title="Recent Uploaded Workbooks"
            subtitle="Securely stored private references ready for profiling and field mapping"
            action={
              <Link
                to="/sources"
                className="text-xs font-semibold text-blue-700 hover:text-blue-900 flex items-center gap-1"
              >
                View all ({totalSources}) <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            }
          >
            {loading ? (
              <div className="py-8 text-center text-sm text-slate-500">Loading workbooks...</div>
            ) : sources.length === 0 ? (
              <div className="py-8 text-center">
                <FileSpreadsheet className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                <p className="text-sm font-medium text-slate-700">No workbooks uploaded yet</p>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  Upload an Excel (.xlsx) file to start schema inspection and profiling.
                </p>
                <Link to="/sources">
                  <Button size="sm" variant="outline" icon={<Upload className="w-3.5 h-3.5" />}>
                    Upload Workbook
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {sources.slice(0, 5).map((source) => (
                  <div key={source.source_id} className="py-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-slate-100 text-slate-700 rounded">
                        <FileSpreadsheet className="w-4 h-4" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-slate-900">
                          {source.original_filename}
                        </div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5">
                          SHA256: {source.sha256.substring(0, 16)}...
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant="neutral">{source.sheets?.length || 0} sheets</Badge>
                      <Link
                        to={`/sources`}
                        className="text-xs font-medium text-blue-700 hover:text-blue-900"
                      >
                        Inspect
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Quick Workflow Navigation */}
        <div>
          <Card title="Migration Pipeline Guide" subtitle="End-to-end migration preparation">
            <ol className="relative border-l border-slate-200 ml-2 space-y-4 my-2 text-xs">
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">1. Upload & Inventory</h4>
                <p className="text-slate-500 mt-0.5">
                  Upload .xlsx workbooks and review automatically discovered sheets and headers.
                </p>
              </li>
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">2. Profile Schema</h4>
                <p className="text-slate-500 mt-0.5">
                  Run worker profiling to analyze column types, null counts, and validation findings.
                </p>
              </li>
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">3. Field Mapping</h4>
                <p className="text-slate-500 mt-0.5">
                  Map source fields to target schema with optional sanitization transforms.
                </p>
              </li>
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">4. Separation of Duties Approval</h4>
                <p className="text-slate-500 mt-0.5">
                  Another designated approver verifies mappings before activation.
                </p>
              </li>
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">5. Preview & Export</h4>
                <p className="text-slate-500 mt-0.5">
                  Generate dry-run transformation results, reconciliation stats, and escaped CSV reports.
                </p>
              </li>
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
};
