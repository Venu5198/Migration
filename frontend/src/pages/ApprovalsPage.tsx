import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Clock,
  Eye,
  GitBranch,
  Lock,
  Search,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { useAuth } from '../context/AuthContext';
import { MappingResponse } from '../types';

export const ApprovalsPage: React.FC = () => {
  const navigate = useNavigate();
  const { session, hasRole } = useAuth();
  const [searchParams] = useSearchParams();
  const initialMappingId = searchParams.get('mappingId') || '';

  const [inputMappingId, setInputMappingId] = useState(initialMappingId);
  const [mapping, setMapping] = useState<MappingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Available Mappings from Local Storage
  const [recentMappings] = useState<MappingResponse[]>(() => {
    const saved = localStorage.getItem('migration_user_mappings');
    return saved ? JSON.parse(saved) : [];
  });

  const loadMapping = async (id: string) => {
    if (!id.trim()) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await apiClient.getMapping(id.trim());
      setMapping(res);
      setInputMappingId(res.mapping_id);
    } catch (err: any) {
      setError(err.message || 'Mapping not found.');
      setMapping(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialMappingId) {
      loadMapping(initialMappingId);
    } else if (recentMappings.length > 0) {
      loadMapping(recentMappings[0].mapping_id);
    }
  }, [initialMappingId]);

  const handleApprove = async () => {
    if (!mapping) return;
    setApproving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await apiClient.approveMapping(mapping.mapping_id);
      setMapping(res);
      setSuccess(`Mapping successfully approved! Upgraded to version ${res.version} and marked immutable.`);

      // Update local storage
      const saved = localStorage.getItem('migration_user_mappings');
      if (saved) {
        const list: MappingResponse[] = JSON.parse(saved);
        const updated = list.map((m) => (m.mapping_id === res.mapping_id ? res : m));
        localStorage.setItem('migration_user_mappings', JSON.stringify(updated));
      }
    } catch (err: any) {
      setError(err.message || 'Approval failed.');
    } finally {
      setApproving(false);
    }
  };

  const isAuthor = mapping?.created_by === session.subject;
  const isApproved = mapping?.status === 'approved';
  const isUnresolved = mapping?.mapping_type === 'unresolved';
  const canApproveRole = hasRole('approver') || hasRole('admin');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Mapping Approvals</h1>
        <p className="text-sm text-slate-500 mt-1">
          Formal sign-off on field mappings. Enforces separation-of-duties: mapping creators cannot approve their own mappings.
        </p>
      </div>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          <div className="space-y-2">
            <div>{error}</div>
            {error.toLowerCase().includes('not found') && (
              <div className="text-xs text-rose-700 bg-rose-100/60 p-2 rounded">
                <strong>Tip:</strong> You might be pasting a <em>Profiling Job UUID</em> or <em>Source Workbook ID</em>. Only <strong>Field Mapping UUIDs</strong> (created on the Field Mapping page) can be approved.
                <div className="mt-2">
                  <Button size="sm" variant="outline" onClick={() => navigate('/mappings')}>
                    Go to Field Mapping &rarr;
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Alert>
      )}
      {success && <Alert type="success" onClose={() => setSuccess(null)}>{success}</Alert>}

      {/* Empty State Helper when no mappings are in workspace */}
      {!mapping && recentMappings.length === 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-700 shrink-0" />
            <div>
              <h4 className="text-sm font-semibold text-amber-900">No Field Mappings Found in Session</h4>
              <p className="text-xs text-amber-700 mt-0.5">
                Before approving, you must first create field mappings connecting source spreadsheet columns to target schemas.
              </p>
            </div>
          </div>
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate('/mappings')}
            icon={<ArrowRight className="w-4 h-4" />}
          >
            Create Field Mappings
          </Button>
        </div>
      )}

      {/* Mapping Lookup / Picker */}
      <Card
        title="Select or Search Mapping for Review"
        subtitle="Search by Mapping UUID (created on the Field Mapping page — do NOT use Job UUID)"
      >
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <input
              type="text"
              value={inputMappingId}
              onChange={(e) => setInputMappingId(e.target.value)}
              placeholder="Paste Field Mapping UUID (from Field Mapping page)"
              className="w-full text-sm font-mono px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <Button
            variant="primary"
            onClick={() => loadMapping(inputMappingId)}
            isLoading={loading}
            icon={<Search className="w-4 h-4" />}
          >
            Load Mapping
          </Button>
        </div>

        {recentMappings.length > 0 && (
          <div className="mt-4 pt-3 border-t border-slate-100">
            <span className="text-xs font-semibold text-slate-500 block mb-2">
              Recent Mappings in Workspace:
            </span>
            <div className="flex flex-wrap gap-2">
              {recentMappings.map((m) => (
                <button
                  key={m.mapping_id}
                  onClick={() => loadMapping(m.mapping_id)}
                  className={`text-xs px-2.5 py-1.5 rounded-md border flex items-center gap-1.5 transition-colors ${
                    mapping?.mapping_id === m.mapping_id
                      ? 'bg-blue-800 text-white border-blue-900 font-semibold'
                      : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <span className="font-semibold">{m.source_field}</span>
                  <span>&rarr;</span>
                  <span>{m.target_field}</span>
                  <Badge variant={m.status === 'approved' ? 'success' : 'neutral'} className="text-[10px]">
                    v{m.version} ({m.status})
                  </Badge>
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Review Details Card */}
      {mapping && (
        <Card
          title={
            <div className="flex items-center gap-3">
              <span>Mapping Review: {mapping.source_field} &rarr; {mapping.target_field}</span>
              <Badge variant={mapping.status === 'approved' ? 'success' : 'warning'}>
                {mapping.status}
              </Badge>
              <Badge variant="navy">Version {mapping.version}</Badge>
            </div>
          }
          subtitle={`Mapping ID: ${mapping.mapping_id}`}
        >
          <div className="space-y-6">
            {/* Meta Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-slate-50 p-4 rounded-md border border-slate-200 text-xs">
              <div>
                <span className="text-slate-400 block font-medium">Source Workbook ID</span>
                <span className="font-mono text-slate-700">{mapping.source_id.substring(0, 10)}...</span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Worksheet</span>
                <span className="font-semibold text-slate-900">{mapping.source_sheet}</span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Created By (Author)</span>
                <span className="font-semibold text-slate-900">{mapping.created_by || 'Unknown'}</span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Mapping Type</span>
                <span className="font-semibold uppercase text-slate-900">{mapping.mapping_type}</span>
              </div>
            </div>

            {/* Validation Rules & Checks */}
            <div className="space-y-3">
              <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Approval Pre-Conditions
              </h4>

              <div className="space-y-2 text-xs">
                {/* Check 1: Mapping Type */}
                <div
                  className={`p-3 rounded border flex items-center justify-between ${
                    isUnresolved
                      ? 'bg-rose-50 border-rose-200 text-rose-900'
                      : 'bg-emerald-50 border-emerald-200 text-emerald-900'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {isUnresolved ? (
                      <AlertCircle className="w-4 h-4 text-rose-600" />
                    ) : (
                      <CheckCircle className="w-4 h-4 text-emerald-600" />
                    )}
                    <span>
                      Mapping Type: <strong>{mapping.mapping_type}</strong>{' '}
                      {isUnresolved && '(Unresolved mappings cannot be approved per contract)'}
                    </span>
                  </div>
                  <Badge variant={isUnresolved ? 'danger' : 'success'}>
                    {isUnresolved ? 'Blocked' : 'Satisfied'}
                  </Badge>
                </div>

                {/* Check 2: Separation of Duties */}
                <div
                  className={`p-3 rounded border flex items-center justify-between ${
                    isAuthor && !isApproved
                      ? 'bg-amber-50 border-amber-200 text-amber-900'
                      : 'bg-emerald-50 border-emerald-200 text-emerald-900'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {isAuthor && !isApproved ? (
                      <AlertTriangle className="w-4 h-4 text-amber-600" />
                    ) : (
                      <CheckCircle className="w-4 h-4 text-emerald-600" />
                    )}
                    <span>
                      Separation of Duties: Creator is <strong>{mapping.created_by}</strong> | Current Actor is{' '}
                      <strong>{session.subject}</strong>{' '}
                      {isAuthor && !isApproved && '(Switch actor in Navbar to simulate peer review)'}
                    </span>
                  </div>
                  <Badge variant={isAuthor && !isApproved ? 'warning' : 'success'}>
                    {isAuthor && !isApproved ? 'Self-Review Detected' : 'Peer Review'}
                  </Badge>
                </div>

                {/* Check 3: Immutability */}
                {isApproved && (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded text-blue-900 flex items-center gap-2">
                    <Lock className="w-4 h-4 text-blue-700" />
                    <span>
                      Approved by <strong>{mapping.approved_by}</strong> on{' '}
                      {new Date(mapping.approved_at!).toLocaleString()}. Approved mappings are immutable.
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Transformations and Notes */}
            {mapping.transformation && (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded text-xs">
                <span className="font-semibold text-slate-700 block mb-1">Transformation Rules:</span>
                <pre className="font-mono text-slate-600">{JSON.stringify(mapping.transformation, null, 2)}</pre>
              </div>
            )}

            {mapping.notes && (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded text-xs">
                <span className="font-semibold text-slate-700 block mb-1">Author Notes:</span>
                <p className="text-slate-600">{mapping.notes}</p>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex items-center justify-between pt-4 border-t border-slate-200">
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate(`/mappings?sourceId=${mapping.source_id}`)}
              >
                Back to Mappings
              </Button>

              <div className="flex items-center gap-3">
                {isApproved ? (
                  <Button
                    variant="primary"
                    icon={<Eye className="w-4 h-4" />}
                    onClick={() =>
                      navigate(`/preview?sourceId=${mapping.source_id}&mappingId=${mapping.mapping_id}`)
                    }
                  >
                    Run Transformation Preview
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    disabled={isUnresolved || approving || !canApproveRole}
                    isLoading={approving}
                    onClick={handleApprove}
                    icon={<UserCheck className="w-4 h-4" />}
                  >
                    Approve Mapping (v{mapping.version + 1})
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};
