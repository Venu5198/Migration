import React, { useEffect, useState } from 'react';
import {
  Calendar,
  ChevronLeft,
  ChevronRight,
  Filter,
  History,
  Lock,
  Search,
  ShieldAlert,
  User,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { useAuth } from '../context/AuthContext';
import { AuditEvent } from '../types';

export const AuditPage: React.FC = () => {
  const { hasRole } = useAuth();
  const isAdmin = hasRole('admin');

  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [entityFilter, setEntityFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAuditEvents = async (pageToLoad = 1, filter = entityFilter) => {
    if (!isAdmin) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.getAuditEvents(filter.trim() || undefined, pageToLoad, pageSize);
      setEvents(res.items);
      setTotal(res.total);
      setPage(res.page);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch audit events.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      loadAuditEvents(1);
    }
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="py-12">
        <Card className="max-w-lg mx-auto text-center p-8">
          <div className="w-12 h-12 bg-rose-50 text-rose-700 rounded-full flex items-center justify-center mx-auto mb-3">
            <Lock className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">Admin Role Required</h2>
          <p className="text-sm text-slate-500 mt-2 mb-4 leading-relaxed">
            Audit lineage records and compliance events are restricted to the <code>admin</code> role. Switch to an admin session in the top navigation bar to inspect audit events.
          </p>
        </Card>
      </div>
    );
  }

  const totalPages = Math.ceil(total / pageSize) || 1;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Audit Lineage Events</h1>
        <p className="text-sm text-slate-500 mt-1">
          Append-only application event log tracking uploads, mapping versions, separation-of-duties approvals, worker execution, and artifact downloads.
        </p>
      </div>

      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Filter Bar */}
      <Card title="Filter Audit Trail">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            loadAuditEvents(1, entityFilter);
          }}
          className="flex flex-col sm:flex-row gap-3"
        >
          <div className="flex-1">
            <input
              type="text"
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value)}
              placeholder="Filter by Entity ID (Source ID, Mapping ID, Job ID...)"
              className="w-full text-sm font-mono px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <Button
            type="submit"
            variant="primary"
            isLoading={loading}
            icon={<Filter className="w-4 h-4" />}
          >
            Filter Events
          </Button>
          {entityFilter && (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setEntityFilter('');
                loadAuditEvents(1, '');
              }}
            >
              Clear
            </Button>
          )}
        </form>
      </Card>

      {/* Events Table */}
      <Card
        title={`Audit Trail Records (${total})`}
        subtitle="Append-only metadata records (cell values and secrets are never stored in audit logs)"
      >
        {loading ? (
          <div className="py-12 text-center text-sm text-slate-500">Loading audit events...</div>
        ) : events.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-500">No audit events found.</div>
        ) : (
          <div className="space-y-4">
            <div className="overflow-x-auto border border-slate-200 rounded-md">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="py-2.5 px-3">Timestamp</th>
                    <th className="py-2.5 px-3">Action</th>
                    <th className="py-2.5 px-3">Actor</th>
                    <th className="py-2.5 px-3">Entity ID</th>
                    <th className="py-2.5 px-3">Job ID</th>
                    <th className="py-2.5 px-3">Metadata</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {events.map((evt, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="py-2 px-3 text-slate-500 whitespace-nowrap">
                        {new Date(evt.timestamp).toLocaleString()}
                      </td>
                      <td className="py-2 px-3">
                        <Badge
                          variant={
                            evt.action.includes('approved')
                              ? 'success'
                              : evt.action.includes('cancel') || evt.action.includes('failed')
                              ? 'danger'
                              : evt.action.includes('exported')
                              ? 'warning'
                              : 'info'
                          }
                        >
                          {evt.action}
                        </Badge>
                      </td>
                      <td className="py-2 px-3 font-semibold text-slate-800">{evt.actor}</td>
                      <td className="py-2 px-3 text-slate-600 truncate max-w-xs">{evt.entity_id}</td>
                      <td className="py-2 px-3 text-slate-400">{evt.job_id || '-'}</td>
                      <td className="py-2 px-3 text-slate-600 font-mono text-[11px] truncate max-w-xs">
                        {evt.metadata ? JSON.stringify(evt.metadata) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between pt-2 text-xs text-slate-600">
              <div>
                Showing page {page} of {totalPages} ({total} total events)
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page <= 1 || loading}
                  onClick={() => loadAuditEvents(page - 1)}
                  icon={<ChevronLeft className="w-3.5 h-3.5" />}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page >= totalPages || loading}
                  onClick={() => loadAuditEvents(page + 1)}
                  icon={<ChevronRight className="w-3.5 h-3.5" />}
                >
                  Next
                </Button>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};
