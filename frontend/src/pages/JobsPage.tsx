import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  Clock,
  Cpu,
  Layers,
  Play,
  RefreshCw,
  RotateCw,
  Search,
  StopCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { JobResponse } from '../types';

export const JobsPage: React.FC = () => {
  const [inputJobId, setInputJobId] = useState('');
  const [job, setJob] = useState<JobResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Recent jobs list
  const [recentJobs, setRecentJobs] = useState<JobResponse[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);
  const [filterKind, setFilterKind] = useState<string>('all');

  const loadRecentJobs = async () => {
    setRecentLoading(true);
    try {
      const params = filterKind === 'all' ? {} : { kind: filterKind };
      const res = await apiClient.listJobs({ ...params, page: 1, page_size: 25 });
      setRecentJobs(res.items);
    } catch {
      // Soft fail
    } finally {
      setRecentLoading(false);
    }
  };

  useEffect(() => {
    loadRecentJobs();
  }, [filterKind]);

  const handleFetchJob = async (idToFetch: string) => {
    if (!idToFetch.trim()) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await apiClient.getJob(idToFetch.trim());
      setJob(res);
      setInputJobId(res.job_id);
    } catch (err: any) {
      setError(err.message || 'Job was not found.');
      setJob(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelJob = async () => {
    if (!job) return;
    setCancelling(true);
    setError(null);
    try {
      const res = await apiClient.cancelJob(job.job_id);
      setJob(res);
      setSuccess('Job cancellation requested successfully.');
      loadRecentJobs();
    } catch (err: any) {
      setError(err.message || 'Failed to cancel job.');
    } finally {
      setCancelling(false);
    }
  };

  const isTerminal =
    job && ['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'CANCELLED'].includes(job.status);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Background Jobs</h1>
        <p className="text-sm text-slate-500 mt-1">
          Inspect asynchronous profiling, preview, and Equus migration worker tasks, monitor lease state, and cancel active jobs.
        </p>
      </div>

      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}
      {success && <Alert type="success" onClose={() => setSuccess(null)}>{success}</Alert>}

      {/* Search Input Card */}
      <Card title="Query Background Job Status">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleFetchJob(inputJobId);
          }}
          className="flex flex-col sm:flex-row gap-3"
        >
          <div className="flex-1">
            <input
              type="text"
              value={inputJobId}
              onChange={(e) => setInputJobId(e.target.value)}
              placeholder="Enter Job UUID (e.g. 550e8400-e29b-41d4-a716-446655440000)"
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
            Inspect Job
          </Button>
        </form>
      </Card>

      {/* Job Details Card */}
      {job && (
        <Card
          title={
            <div className="flex items-center gap-3">
              <span className="font-semibold text-slate-900">
                {job.kind.toUpperCase()} Job Details
              </span>
              <Badge
                variant={
                  job.status === 'COMPLETED'
                    ? 'success'
                    : job.status === 'COMPLETED_WITH_ERRORS'
                    ? 'warning'
                    : job.status === 'FAILED'
                    ? 'danger'
                    : job.status === 'CANCELLED'
                    ? 'neutral'
                    : 'navy'
                }
              >
                {job.status}
              </Badge>
            </div>
          }
          subtitle={`Job ID: ${job.job_id}`}
          action={
            !isTerminal ? (
              <Button
                variant="danger"
                size="sm"
                onClick={handleCancelJob}
                isLoading={cancelling}
                icon={<StopCircle className="w-3.5 h-3.5" />}
              >
                Cancel Job
              </Button>
            ) : null
          }
        >
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-slate-50 p-4 rounded-md border border-slate-200 text-xs">
              <div>
                <span className="text-slate-400 block font-medium">Source ID</span>
                <span className="font-mono text-slate-700">{job.source_id.substring(0, 10)}...</span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Source Filename</span>
                <span className="font-semibold text-slate-800">
                  {job.source_filename || job.result?.source_name || 'N/A'}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Execution Progress</span>
                <span className="font-semibold text-slate-900">{job.progress}%</span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Claim Attempts</span>
                <span className="font-semibold text-slate-900">{job.attempts}</span>
              </div>
            </div>

            {/* Timestamps */}
            <div className="flex flex-wrap gap-6 text-xs text-slate-500">
              <div className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                <span>Created: {new Date(job.created_at).toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <RotateCw className="w-3.5 h-3.5 text-slate-400" />
                <span>Updated: {new Date(job.updated_at).toLocaleString()}</span>
              </div>
            </div>

            {/* Failure Code */}
            {job.failure_code && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded text-xs text-rose-800">
                <span className="font-semibold mr-1">Failure Code:</span>
                <span>{job.failure_code}</span>
              </div>
            )}

            {/* Result Object */}
            {job.result && (
              <div>
                <h4 className="text-xs font-semibold text-slate-700 uppercase mb-2">
                  Job Result Output
                </h4>
                <pre className="p-4 bg-slate-900 text-slate-100 rounded-md font-mono text-xs overflow-x-auto max-h-72">
                  {JSON.stringify(job.result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Recent Jobs Table */}
      <Card
        title="Recent Worker Jobs"
        subtitle="Live jobs registered across worker processes"
        action={
          <div className="flex items-center gap-2">
            <select
              value={filterKind}
              onChange={(e) => setFilterKind(e.target.value)}
              className="text-xs border border-slate-300 rounded px-2 py-1 bg-white"
            >
              <option value="all">All Kinds</option>
              <option value="equus_migration">Equus Migration</option>
              <option value="profile">Profile</option>
              <option value="preview">Preview</option>
            </select>
            <Button
              size="sm"
              variant="outline"
              onClick={loadRecentJobs}
              isLoading={recentLoading}
              icon={<RefreshCw className={`w-3.5 h-3.5 ${recentLoading ? 'animate-spin' : ''}`} />}
            >
              Refresh
            </Button>
          </div>
        }
      >
        {recentLoading && recentJobs.length === 0 ? (
          <div className="py-8 text-center text-sm text-slate-500">Loading jobs...</div>
        ) : recentJobs.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-500">No jobs found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-700 uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Job ID</th>
                  <th className="py-2.5 px-3">Kind</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Created</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-800">
                {recentJobs.map((j) => (
                  <tr key={j.job_id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">
                      {j.job_id.substring(0, 8)}...
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-slate-900 capitalize">
                      {j.kind.replace('_', ' ')}
                    </td>
                    <td className="py-2.5 px-3">
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
                    </td>
                    <td className="py-2.5 px-3 text-slate-500">
                      {new Date(j.created_at).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleFetchJob(j.job_id)}
                      >
                        Inspect
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
