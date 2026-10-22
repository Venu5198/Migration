import React, { useState } from 'react';
import {
  AlertCircle,
  Clock,
  Cpu,
  Play,
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
          Inspect asynchronous profiling and transformation worker tasks, view execution leases, attempts, and cancel active jobs.
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
                    : 'info'
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
                <span className="text-slate-400 block font-medium">Execution Progress</span>
                <span className="font-semibold text-slate-900">{job.progress}%</span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Claim Attempts</span>
                <span className="font-semibold text-slate-900">{job.attempts}</span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Cancellation Requested</span>
                <span className="font-semibold text-slate-900">
                  {job.cancellation_requested ? 'Yes' : 'No'}
                </span>
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
    </div>
  );
};
