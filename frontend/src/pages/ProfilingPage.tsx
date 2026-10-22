import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  BarChart2,
  CheckCircle2,
  Clock,
  Layers,
  Play,
  RotateCw,
  Search,
  StopCircle,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { JobResponse, ProfileResult, SourceResponse } from '../types';

export const ProfilingPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialSourceId = searchParams.get('sourceId') || '';

  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<string>(initialSourceId);
  const [loadingSources, setLoadingSources] = useState(false);

  // Job & Polling State
  const [activeJob, setActiveJob] = useState<JobResponse | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSources = async () => {
      setLoadingSources(true);
      try {
        const res = await apiClient.listSources(1, 100);
        setSources(res.items);
        if (!selectedSourceId && res.items.length > 0) {
          setSelectedSourceId(res.items[0].source_id);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load sources.');
      } finally {
        setLoadingSources(false);
      }
    };
    fetchSources();
  }, []);

  // Poll active job until terminal state
  useEffect(() => {
    if (!activeJob) return;
    const isTerminal = ['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'CANCELLED'].includes(
      activeJob.status
    );
    if (isTerminal) return;

    const interval = setInterval(async () => {
      try {
        const updated = await apiClient.getJob(activeJob.job_id);
        setActiveJob(updated);
      } catch (err: any) {
        console.error('Job polling error:', err);
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [activeJob?.job_id, activeJob?.status]);

  const handleStartProfiling = async () => {
    if (!selectedSourceId) return;
    setIsStarting(true);
    setError(null);
    try {
      const job = await apiClient.startProfileJob(selectedSourceId);
      setActiveJob(job);
    } catch (err: any) {
      setError(err.message || 'Failed to trigger profiling job.');
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancelJob = async () => {
    if (!activeJob) return;
    setIsCancelling(true);
    try {
      const updated = await apiClient.cancelJob(activeJob.job_id);
      setActiveJob(updated);
    } catch (err: any) {
      setError(err.message || 'Failed to cancel job.');
    } finally {
      setIsCancelling(false);
    }
  };

  const profileResult: ProfileResult | undefined =
    activeJob?.status === 'COMPLETED' || activeJob?.status === 'COMPLETED_WITH_ERRORS'
      ? activeJob.result
      : undefined;

  // Extract sheet nulls if available
  const sheetNulls: Record<string, number> =
    profileResult?.sheets?.[0]?.null_counts || profileResult?.null_counts || {};

  // Null counts chart data
  const nullChartData = Object.entries(sheetNulls).map(([key, val]) => ({
    name: key,
    nulls: val,
  }));

  const selectedSource = sources.find((s) => s.source_id === selectedSourceId);

  const totalEvaluatedRows =
    profileResult?.sheets?.reduce((acc, s) => acc + (s.populated_rows || 0), 0) ??
    profileResult?.row_count ??
    selectedSource?.sheets?.[0]?.max_row ??
    0;

  const totalColumnsProfiled =
    Object.keys(sheetNulls).length ||
    profileResult?.column_count ||
    selectedSource?.sheets?.[0]?.max_column ||
    0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Data Profiling</h1>
        <p className="text-sm text-slate-500 mt-1">
          Worker-driven asynchronous profiling. Inspect field statistics, null ratios, inferred data types, and structural findings.
        </p>
      </div>

      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Source Selection & Trigger */}
      <Card title="Start Worker Profiling Job">
        <div className="flex flex-col sm:flex-row gap-4 items-center">
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Select Source Workbook
            </label>
            <select
              value={selectedSourceId}
              onChange={(e) => setSelectedSourceId(e.target.value)}
              disabled={Boolean(loadingSources || isStarting || (activeJob && !['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'CANCELLED'].includes(activeJob.status)))}
              className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white"
            >
              {sources.map((s) => (
                <option key={s.source_id} value={s.source_id}>
                  {s.original_filename} ({s.sheets?.length || 0} sheets) — {s.source_id.substring(0, 8)}...
                </option>
              ))}
            </select>
          </div>

          <div className="self-end w-full sm:w-auto">
            <Button
              variant="primary"
              disabled={!selectedSourceId || isStarting}
              isLoading={isStarting}
              onClick={handleStartProfiling}
              icon={<Play className="w-4 h-4" />}
            >
              Start Profiling Job (202 Accepted)
            </Button>
          </div>
        </div>
      </Card>

      {/* Active Job Status */}
      {activeJob && (
        <Card
          title={
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-slate-500">Job: {activeJob.job_id}</span>
              <Badge
                variant={
                  activeJob.status === 'COMPLETED'
                    ? 'success'
                    : activeJob.status === 'COMPLETED_WITH_ERRORS'
                    ? 'warning'
                    : activeJob.status === 'FAILED'
                    ? 'danger'
                    : activeJob.status === 'CANCELLED'
                    ? 'neutral'
                    : 'info'
                }
              >
                {activeJob.status}
              </Badge>
            </div>
          }
          action={
            !['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'CANCELLED'].includes(activeJob.status) ? (
              <Button
                variant="danger"
                size="sm"
                onClick={handleCancelJob}
                isLoading={isCancelling}
                icon={<StopCircle className="w-3.5 h-3.5" />}
              >
                Cancel Job
              </Button>
            ) : null
          }
        >
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
            <div>
              <span className="text-slate-400 block font-medium">Job Kind</span>
              <span className="font-semibold text-slate-800 uppercase">{activeJob.kind}</span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">Worker Progress</span>
              <span className="font-semibold text-slate-800">{activeJob.progress}%</span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">Claim Attempts</span>
              <span className="font-semibold text-slate-800">{activeJob.attempts}</span>
            </div>
            <div>
              <span className="text-slate-400 block font-medium">Updated At</span>
              <span className="text-slate-600">{new Date(activeJob.updated_at).toLocaleTimeString()}</span>
            </div>
          </div>

          {activeJob.failure_code && (
            <div className="mt-3 p-3 bg-rose-50 border border-rose-200 rounded text-xs text-rose-800">
              <span className="font-semibold">Failure Code:</span> {activeJob.failure_code}
            </div>
          )}
        </Card>
      )}

      {/* Profiling Results Display */}
      {profileResult && (
        <div className="space-y-6">
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Card className="border-l-4 border-l-blue-800">
              <span className="text-xs font-semibold text-slate-500 uppercase">Evaluated Rows</span>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {totalEvaluatedRows}
              </div>
            </Card>

            <Card className="border-l-4 border-l-emerald-600">
              <span className="text-xs font-semibold text-slate-500 uppercase">Columns Profiled</span>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {totalColumnsProfiled}
              </div>
            </Card>

            <Card className="border-l-4 border-l-amber-500">
              <span className="text-xs font-semibold text-slate-500 uppercase">Total Findings</span>
              <div className="text-2xl font-bold text-slate-900 mt-1">
                {profileResult.issues?.length || 0}
              </div>
            </Card>

            <Card className="border-l-4 border-l-purple-600">
              <span className="text-xs font-semibold text-slate-500 uppercase">Execution Target</span>
              <div className="text-2xl font-bold text-purple-900 mt-1">Dry Run</div>
            </Card>
          </div>

          {/* Sheet Breakdown if multiple/available */}
          {profileResult.sheets && profileResult.sheets.length > 0 && (
            <Card title="Worksheet Metrics Summary" subtitle="Profile statistics per individual worksheet">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Sheet Name</th>
                      <th className="py-2.5 px-3">Populated Rows</th>
                      <th className="py-2.5 px-3">Structural Empty Rows</th>
                      <th className="py-2.5 px-3">Duplicate Rows</th>
                      <th className="py-2.5 px-3">Columns Profiled</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {profileResult.sheets.map((s, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2 px-3 font-semibold text-slate-800">{s.sheet}</td>
                        <td className="py-2 px-3 text-slate-700">{s.populated_rows}</td>
                        <td className="py-2 px-3 text-slate-500">{s.empty_structural_rows}</td>
                        <td className="py-2 px-3 text-slate-500">{s.duplicate_rows}</td>
                        <td className="py-2 px-3 text-slate-500">{Object.keys(s.null_counts || {}).length}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Null Counts Chart & Inferred Types */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card title="Missing / Null Counts by Field" subtitle="Columns with detected empty values">
              {nullChartData.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500">No null values found across profiled rows.</div>
              ) : (
                <div className="h-64 w-full pt-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={nullChartData} margin={{ top: 10, right: 10, left: -20, bottom: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="name" angle={-30} textAnchor="end" interval={0} tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="nulls" fill="#2563eb" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>

            <Card title="Inferred Schema Types" subtitle="Detected types per header">
              <div className="max-h-64 overflow-y-auto divide-y divide-slate-100 text-xs">
                {Object.entries(profileResult.type_profile || {}).map(([col, typ]) => (
                  <div key={col} className="py-2.5 flex items-center justify-between">
                    <span className="font-semibold text-slate-800">{col}</span>
                    <Badge variant="navy">{typ}</Badge>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* Sample Values Table */}
          {profileResult.sample_values && Object.keys(profileResult.sample_values).length > 0 && (
            <Card title="Field Sample Values" subtitle="First parsed unique values per column">
              <div className="border border-slate-200 rounded-md overflow-hidden max-h-60 overflow-y-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Field Name</th>
                      <th className="py-2.5 px-3">Sample Values</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {Object.entries(profileResult.sample_values).map(([col, vals]) => (
                      <tr key={col} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-semibold text-slate-900 w-1/3">{col}</td>
                        <td className="py-2.5 px-3 text-slate-600 font-mono">
                          {Array.isArray(vals) ? vals.map(String).join(', ') : String(vals)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Findings List */}
          {profileResult.issues && profileResult.issues.length > 0 && (
            <Card title="Validation Issues & Findings" subtitle="Quality alerts generated during profiling">
              <div className="space-y-2">
                {profileResult.issues.map((issue: any, idx: number) => {
                  const text = typeof issue === 'string' ? issue : issue.message || JSON.stringify(issue);
                  return (
                    <div
                      key={idx}
                      className="p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900 flex items-start gap-2"
                    >
                      <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                      <span>{text}</span>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};
