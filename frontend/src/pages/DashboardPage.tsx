import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle,
  CheckCircle2,
  Clock,
  Database,
  FileCheck,
  FileSpreadsheet,
  GitBranch,
  Layers,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Upload,
  XCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { HealthResponse, JobResponse, SourceResponse } from '../types';

export const DashboardPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [totalSources, setTotalSources] = useState(0);

  // Migration metrics
  const [migrationJobs, setMigrationJobs] = useState<JobResponse[]>([]);
  const [totalMigrationJobs, setTotalMigrationJobs] = useState(0);

  useEffect(() => {
    const loadDashboardData = async () => {
      setLoading(true);
      try {
        const [healthRes, sourcesRes, jobsRes] = await Promise.all([
          apiClient.getHealth().catch(() => null),
          apiClient.listSources(1, 10).catch(() => ({ items: [], total: 0, page: 1, page_size: 10 })),
          apiClient.listJobs({ kind: 'equus_migration', page: 1, page_size: 50 }).catch(() => ({
            items: [],
            total: 0,
            page: 1,
            page_size: 50,
          })),
        ]);
        if (healthRes) setHealth(healthRes);
        setSources(sourcesRes.items);
        setTotalSources(sourcesRes.total);
        setMigrationJobs(jobsRes.items);
        setTotalMigrationJobs(jobsRes.total);
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  // Compute Migration Job Metrics
  const completedJobs = migrationJobs.filter(
    (j) => j.status === 'COMPLETED' || j.status === 'COMPLETED_WITH_ERRORS'
  ).length;
  const failedJobs = migrationJobs.filter((j) => j.status === 'FAILED').length;
  const processingJobs = migrationJobs.filter((j) =>
    ['PENDING', 'QUEUED', 'RUNNING'].includes(j.status)
  ).length;

  const latestJob = migrationJobs[0] || null;
  const latestRecon = latestJob?.result?.reconciliation || null;
  const latestCoverage = latestJob?.result?.coverage_percentage ?? null;

  return (
    <div className="space-y-6">
      {/* Top Welcome & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Migration Overview</h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time status of Topia-to-Equus migrations, background worker pipelines, and reconciliation results.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/migration">
            <Button variant="primary" icon={<Layers className="w-4 h-4" />}>
              Run Equus Migration
            </Button>
          </Link>
          <Link to="/sources">
            <Button variant="outline" icon={<Upload className="w-4 h-4" />}>
              Upload Workbook
            </Button>
          </Link>
        </div>
      </div>

      {/* Security Banner */}
      <Alert type="warning" title="Equus Target Writes Strictly Disabled">
        All migration transformations execute deterministically into timestamped import artifacts. Direct target API writes remain isolated by contract.
      </Alert>

      {/* Primary Metrics Grid: Actual Backend Migration Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Migration Jobs */}
        <Card className="border-l-4 border-l-blue-800">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Total Migrations
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {loading ? '...' : totalMigrationJobs}
              </div>
              <div className="text-xs text-slate-500 mt-1 space-x-1.5">
                <span className="text-emerald-700 font-medium">{completedJobs} completed</span>
                <span>•</span>
                <span className={failedJobs > 0 ? 'text-rose-600 font-medium' : 'text-slate-400'}>
                  {failedJobs} failed
                </span>
                {processingJobs > 0 && (
                  <>
                    <span>•</span>
                    <span className="text-blue-700 font-medium">{processingJobs} active</span>
                  </>
                )}
              </div>
            </div>
            <div className="p-3 bg-blue-50 text-blue-800 rounded-lg">
              <Layers className="w-6 h-6" />
            </div>
          </div>
        </Card>

        {/* Latest Migration Status */}
        <Card className="border-l-4 border-l-emerald-600">
          <div className="flex items-center justify-between">
            <div className="w-full mr-2">
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Latest Migration Status
              </div>
              <div className="mt-1 flex items-center gap-2">
                {loading ? (
                  <span className="text-sm text-slate-400">Loading...</span>
                ) : latestJob ? (
                  <>
                    <Badge
                      variant={
                        latestJob.status === 'COMPLETED'
                          ? 'success'
                          : latestJob.status === 'COMPLETED_WITH_ERRORS'
                          ? 'warning'
                          : latestJob.status === 'FAILED'
                          ? 'danger'
                          : 'navy'
                      }
                    >
                      {latestJob.status}
                    </Badge>
                    <span className="text-xs text-slate-600 truncate font-medium">
                      {latestJob.source_filename || latestJob.result?.source_name || 'Topia'}
                    </span>
                  </>
                ) : (
                  <span className="text-sm text-slate-500">None executed yet</span>
                )}
              </div>
              <div className="text-xs text-slate-400 mt-1">
                {latestJob ? new Date(latestJob.created_at).toLocaleString() : 'No runs on record'}
              </div>
            </div>
            <div className="p-3 bg-emerald-50 text-emerald-700 rounded-lg shrink-0">
              <FileCheck className="w-6 h-6" />
            </div>
          </div>
        </Card>

        {/* Latest Reconciliation Result */}
        <Card className="border-l-4 border-l-purple-600">
          <div className="flex items-center justify-between">
            <div className="w-full mr-2">
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Latest Reconciliation
              </div>
              <div className="mt-1">
                {loading ? (
                  <span className="text-sm text-slate-400">Loading...</span>
                ) : latestRecon ? (
                  <div className="flex items-center gap-2">
                    <Badge variant={latestRecon.is_valid ? 'success' : 'danger'}>
                      {latestRecon.is_valid ? 'PASSED' : 'FAILED'}
                    </Badge>
                    <span className="text-xs text-slate-600">
                      {latestRecon.is_valid
                        ? '100% Relational Parity'
                        : `${latestRecon.errors?.length || 0} error(s)`}
                    </span>
                  </div>
                ) : (
                  <span className="text-sm text-slate-500">N/A</span>
                )}
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {latestJob?.result
                  ? `${latestJob.result.insert_records ?? 0} INSERT / ${latestJob.result.update_records ?? 0} UPDATE`
                  : 'Pending run'}
              </div>
            </div>
            <div className="p-3 bg-purple-50 text-purple-700 rounded-lg shrink-0">
              <CheckCircle2 className="w-6 h-6" />
            </div>
          </div>
        </Card>

        {/* Mapping Coverage */}
        <Card className="border-l-4 border-l-amber-500">
          <div className="flex items-center justify-between">
            <div className="w-full mr-2">
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Equus Coverage
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {loading ? '...' : latestCoverage !== null ? `${latestCoverage.toFixed(1)}%` : 'N/A'}
              </div>
              <div className="w-full bg-slate-100 rounded-full h-1.5 mt-2">
                <div
                  className="bg-amber-600 h-1.5 rounded-full"
                  style={{ width: `${Math.min(100, latestCoverage || 0)}%` }}
                />
              </div>
            </div>
            <div className="p-3 bg-amber-50 text-amber-700 rounded-lg shrink-0">
              <BarChart3 className="w-6 h-6" />
            </div>
          </div>
        </Card>
      </div>

      {/* Main Two Column Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Recent Migration Jobs */}
        <div className="lg:col-span-2 space-y-6">
          <Card
            title="Recent Equus Migration Runs"
            subtitle="Asynchronous pipeline executions and generated import workbooks"
            action={
              <Link
                to="/migration?tab=history"
                className="text-xs font-semibold text-blue-700 hover:text-blue-900 flex items-center gap-1"
              >
                View all ({totalMigrationJobs}) <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            }
          >
            {loading ? (
              <div className="py-8 text-center text-sm text-slate-500">Loading migration jobs...</div>
            ) : migrationJobs.length === 0 ? (
              <div className="py-8 text-center">
                <Layers className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                <p className="text-sm font-medium text-slate-700">No migrations executed yet</p>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  Run your first Topia-to-Equus migration to produce import workbooks and mapping reports.
                </p>
                <Link to="/migration">
                  <Button size="sm" variant="primary" icon={<PlayCircle className="w-3.5 h-3.5" />}>
                    Start First Migration
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {migrationJobs.slice(0, 5).map((j) => {
                  const jRecon = j.result?.reconciliation;
                  const isReconPass = jRecon?.is_valid === true;

                  return (
                    <div key={j.job_id} className="py-3 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-50 text-blue-800 rounded">
                          <Layers className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-sm font-semibold text-slate-900">
                            {j.source_filename || j.result?.source_name || 'Topia Export'}
                          </div>
                          <div className="text-xs text-slate-400 font-mono mt-0.5">
                            ID: {j.job_id.substring(0, 8)}... • {new Date(j.created_at).toLocaleDateString()}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <Badge
                          variant={
                            j.status === 'COMPLETED'
                              ? 'success'
                              : j.status === 'COMPLETED_WITH_ERRORS'
                              ? 'warning'
                              : j.status === 'FAILED'
                              ? 'danger'
                              : 'navy'
                          }
                        >
                          {j.status}
                        </Badge>
                        {jRecon && (
                          <Badge variant={isReconPass ? 'success' : 'danger'}>
                            {isReconPass ? 'Recon Pass' : 'Recon Fail'}
                          </Badge>
                        )}
                        <Link
                          to={`/migration?tab=details&jobId=${j.job_id}`}
                          className="text-xs font-medium text-blue-700 hover:text-blue-900"
                        >
                          Inspect
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* Uploaded Workbooks Inventory */}
          <Card
            title="Source Workbooks Inventory"
            subtitle="Stored Excel workbooks ready for schema inspection or migration"
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
              <div className="py-6 text-center text-sm text-slate-500">Loading workbooks...</div>
            ) : sources.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-500">
                No workbooks uploaded yet.
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {sources.slice(0, 3).map((source) => (
                  <div key={source.source_id} className="py-2.5 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2.5">
                      <FileSpreadsheet className="w-4 h-4 text-blue-800 shrink-0" />
                      <span className="font-semibold text-slate-900">
                        {source.original_filename}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400 font-mono">
                        {source.sheets?.length || 0} sheets
                      </span>
                      <Link
                        to="/sources"
                        className="text-blue-700 hover:text-blue-900 font-medium ml-2"
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

        {/* Right Info Rail */}
        <div className="space-y-6">
          <Card title="Topia → Equus Guide" subtitle="Direct workflow overview">
            <ol className="relative border-l border-slate-200 ml-2 space-y-4 my-2 text-xs">
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">1. Upload Topia Export</h4>
                <p className="text-slate-500 mt-0.5">
                  Select Full Historical Past Assignment export (.xlsx) with multi-row headers.
                </p>
              </li>
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">2. Select Identifier Strategy</h4>
                <p className="text-slate-500 mt-0.5">
                  Choose Option B (Employee Number in Assignment ID) or Option A (Topia ID).
                </p>
              </li>
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">3. Execute Transformation</h4>
                <p className="text-slate-500 mt-0.5">
                  Worker generates 1 INSERT row per assignment plus secondary UPDATE records.
                </p>
              </li>
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">4. Review Reconciliation</h4>
                <p className="text-slate-500 mt-0.5">
                  Verify relational balance, coverage %, and absence of orphan updates.
                </p>
              </li>
              <li className="ml-4">
                <div className="absolute -left-1.5 mt-0.5 w-3 h-3 bg-blue-800 rounded-full border border-white" />
                <h4 className="font-semibold text-slate-900">5. Download Artifacts</h4>
                <p className="text-slate-500 mt-0.5">
                  Retrieve Equus Import workbook (.xlsx) and Excel Mapping Report.
                </p>
              </li>
            </ol>
          </Card>

          <Card title="Target Connector Safety">
            <div className="space-y-3 text-xs text-slate-600">
              <div className="flex items-center gap-2 font-semibold text-slate-800">
                <Database className="w-4 h-4 text-emerald-600" />
                <span>MongoDB Storage Status</span>
              </div>
              <p className="text-slate-500 text-[11px] leading-relaxed">
                Database: <span className="font-semibold text-slate-700 capitalize">{health?.database || 'Connected'}</span>. All job state, audit events, and checksums are safely preserved.
              </p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
