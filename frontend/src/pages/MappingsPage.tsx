import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  CheckCircle,
  Clock,
  Edit3,
  ExternalLink,
  FileSpreadsheet,
  GitBranch,
  History,
  Layers,
  Plus,
  Save,
  ShieldCheck,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { Modal } from '../components/common/Modal';
import { MappingCreate, MappingResponse, MappingType, SheetSchema, SourceResponse } from '../types';

export const MappingsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialSourceId = searchParams.get('sourceId') || '';
  const initialSheet = searchParams.get('sheet') || '';

  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<string>(initialSourceId);
  const [selectedSheetName, setSelectedSheetName] = useState<string>(initialSheet);

  // Form Fields
  const [sourceEntity, setSourceEntity] = useState('Employee');
  const [sourceField, setSourceField] = useState('');
  const [targetEntity, setTargetEntity] = useState('Employee');
  const [targetField, setTargetField] = useState('');
  const [mappingType, setMappingType] = useState<MappingType>('direct');
  const [isRequired, setIsRequired] = useState(false);
  const [notes, setNotes] = useState('');

  // Transformations
  const [enableTrim, setEnableTrim] = useState(false);
  const [enableCase, setEnableCase] = useState<'none' | 'uppercase' | 'lowercase'>('none');
  const [valueMapJson, setValueMapJson] = useState('');

  // Created Mappings in Session
  const [sessionMappings, setSessionMappings] = useState<MappingResponse[]>(() => {
    const saved = localStorage.getItem('migration_user_mappings');
    return saved ? JSON.parse(saved) : [];
  });

  // State
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Version History Modal
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [versions, setVersions] = useState<MappingResponse[]>([]);
  const [activeMappingForHistory, setActiveMappingForHistory] = useState<string | null>(null);

  useEffect(() => {
    const fetchSources = async () => {
      setLoading(true);
      try {
        const res = await apiClient.listSources(1, 100);
        setSources(res.items);
        if (!selectedSourceId && res.items.length > 0) {
          setSelectedSourceId(res.items[0].source_id);
        }
        const activeSrc = res.items.find((s) => s.source_id === (selectedSourceId || res.items[0]?.source_id)) || res.items[0];
        if (activeSrc?.sheets?.[0]?.name && !selectedSheetName) {
          setSelectedSheetName(activeSrc.sheets[0].name);
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load workbooks.');
      } finally {
        setLoading(false);
      }
    };
    fetchSources();
  }, []);

  const currentSource = sources.find((s) => s.source_id === selectedSourceId);
  const currentSheet = currentSource?.sheets?.find((sh) => sh.name === selectedSheetName) || currentSource?.sheets?.[0];
  const availableHeaders = currentSheet?.headers || [];

  useEffect(() => {
    if (availableHeaders.length > 0 && !availableHeaders.includes(sourceField)) {
      setSourceField(availableHeaders[0]);
    }
  }, [availableHeaders, sourceField]);

  const saveMappingToSession = (mapping: MappingResponse) => {
    setSessionMappings((prev) => {
      const filtered = prev.filter((m) => m.mapping_id !== mapping.mapping_id);
      const updated = [mapping, ...filtered];
      localStorage.setItem('migration_user_mappings', JSON.stringify(updated));
      return updated;
    });
  };

  const handleCreateMapping = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSourceId || !currentSheet) {
      setError('Please select a valid source workbook and worksheet.');
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    // Build transformation payload
    let transformation: Record<string, any> | null = null;
    if (mappingType === 'transformed') {
      transformation = {};
      if (enableTrim) transformation.trim = true;
      if (enableCase === 'uppercase') transformation.uppercase = true;
      if (enableCase === 'lowercase') transformation.lowercase = true;

      if (valueMapJson.trim()) {
        try {
          transformation.value_map = JSON.parse(valueMapJson);
        } catch {
          setError('Value Map must be valid JSON (e.g. {"US": "USA", "UK": "GBR"}).');
          setSaving(false);
          return;
        }
      }
    }

    const payload: MappingCreate = {
      source_id: selectedSourceId,
      source_entity: sourceEntity,
      source_sheet: currentSheet.name,
      source_field: sourceField,
      target_entity: targetEntity,
      target_field: targetField.trim(),
      mapping_type: mappingType,
      required: isRequired,
      transformation: transformation && Object.keys(transformation).length > 0 ? transformation : null,
      notes: notes.trim() || null,
    };

    try {
      const res = await apiClient.createMapping(payload);
      saveMappingToSession(res);
      setSuccess(`Mapping created successfully! ID: ${res.mapping_id} (Version ${res.version}, Status: ${res.status}).`);
    } catch (err: any) {
      setError(err.message || 'Failed to create field mapping.');
    } finally {
      setSaving(false);
    }
  };

  const handleViewVersions = async (mappingId: string) => {
    setActiveMappingForHistory(mappingId);
    try {
      const list = await apiClient.getMappingVersions(mappingId);
      setVersions(list);
      setHistoryModalOpen(true);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch version history.');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Field Mappings</h1>
        <p className="text-sm text-slate-500 mt-1">
          Map source worksheet fields to target entity structures. Unresolved fields propose candidate mappings pending client confirmation.
        </p>
      </div>

      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}
      {success && <Alert type="success" onClose={() => setSuccess(null)}>{success}</Alert>}

      {/* Mapping Creation Form */}
      <Card title="Create New Field Mapping" subtitle="Validated against actual source workbook sheet headers">
        <form onSubmit={handleCreateMapping} className="space-y-5">
          {/* Row 1: Source & Sheet */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Source Workbook
              </label>
              <select
                value={selectedSourceId}
                onChange={(e) => {
                  setSelectedSourceId(e.target.value);
                  const src = sources.find((s) => s.source_id === e.target.value);
                  if (src?.sheets?.[0]?.name) setSelectedSheetName(src.sheets[0].name);
                }}
                className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white"
                required
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
                Worksheet
              </label>
              <select
                value={selectedSheetName}
                onChange={(e) => setSelectedSheetName(e.target.value)}
                className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white"
                required
              >
                {currentSource?.sheets?.map((sh) => (
                  <option key={sh.name} value={sh.name}>
                    {sh.name} ({sh.max_row} rows, {sh.headers.length} headers)
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Row 2: Source Field & Entity */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Source Field (from Sheet Headers)
              </label>
              {availableHeaders.length > 0 ? (
                <select
                  value={sourceField}
                  onChange={(e) => setSourceField(e.target.value)}
                  className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white font-medium"
                  required
                >
                  {availableHeaders.map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={sourceField}
                  onChange={(e) => setSourceField(e.target.value)}
                  placeholder="e.g. Employee ID"
                  className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  required
                />
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Source Entity
              </label>
              <input
                type="text"
                value={sourceEntity}
                onChange={(e) => setSourceEntity(e.target.value)}
                className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="e.g. Employee"
                required
              />
            </div>
          </div>

          {/* Row 3: Target Field & Entity */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Target Field
              </label>
              <input
                type="text"
                value={targetField}
                onChange={(e) => setTargetField(e.target.value)}
                placeholder="e.g. employee_id, first_name, country_code"
                className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none font-medium"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Target Entity
              </label>
              <input
                type="text"
                value={targetEntity}
                onChange={(e) => setTargetEntity(e.target.value)}
                className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="e.g. Employee"
                required
              />
            </div>
          </div>

          {/* Row 4: Mapping Type & Requirements */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Mapping Type
              </label>
              <select
                value={mappingType}
                onChange={(e) => setMappingType(e.target.value as MappingType)}
                className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white font-medium"
              >
                <option value="direct">direct (straight copy, no transforms)</option>
                <option value="transformed">transformed (trim, case, value_map)</option>
                <option value="derived">derived (formula / compound field)</option>
                <option value="excluded">excluded (explicitly dropped)</option>
                <option value="unresolved">unresolved (pending client decisions)</option>
              </select>
            </div>

            <div className="flex items-center pt-6">
              <label className="flex items-center gap-2 cursor-pointer text-sm font-medium text-slate-800">
                <input
                  type="checkbox"
                  checked={isRequired}
                  onChange={(e) => setIsRequired(e.target.checked)}
                  className="rounded border-slate-300 text-blue-800 focus:ring-blue-500 w-4 h-4"
                />
                <span>Target Required Field (fails preview if missing)</span>
              </label>
            </div>
          </div>

          {/* Transformation Config (if transformed) */}
          {mappingType === 'transformed' && (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-md space-y-3">
              <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                Transformation Rules
              </span>

              <div className="flex flex-wrap gap-4 text-xs font-medium text-slate-700">
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={enableTrim}
                    onChange={(e) => setEnableTrim(e.target.checked)}
                    className="rounded border-slate-300 text-blue-800 focus:ring-blue-500"
                  />
                  <span>Trim whitespace</span>
                </label>

                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    name="caseTransform"
                    checked={enableCase === 'uppercase'}
                    onChange={() => setEnableCase('uppercase')}
                  />
                  <span>Uppercase</span>
                </label>

                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    name="caseTransform"
                    checked={enableCase === 'lowercase'}
                    onChange={() => setEnableCase('lowercase')}
                  />
                  <span>Lowercase</span>
                </label>

                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    name="caseTransform"
                    checked={enableCase === 'none'}
                    onChange={() => setEnableCase('none')}
                  />
                  <span>None</span>
                </label>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                  Value Map Dictionary (JSON)
                </label>
                <input
                  type="text"
                  value={valueMapJson}
                  onChange={(e) => setValueMapJson(e.target.value)}
                  placeholder='{"US": "USA", "UK": "GBR"}'
                  className="w-full text-xs font-mono px-3 py-2 border border-slate-300 rounded bg-white focus:outline-none"
                />
              </div>
            </div>
          )}

          {/* Notes */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Audit / Design Notes (Optional)
            </label>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Mapped pending confirmation of country code dictionary."
              className="w-full text-xs px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <div className="flex justify-end pt-2">
            <Button
              type="submit"
              variant="primary"
              disabled={saving}
              isLoading={saving}
              icon={<Save className="w-4 h-4" />}
            >
              Save Mapping (Draft)
            </Button>
          </div>
        </form>
      </Card>

      {/* Session Mappings Table */}
      <Card
        title={`Configured Mappings (${sessionMappings.length})`}
        subtitle="Mappings created in your session ready for approval review and preview dry-runs"
      >
        {sessionMappings.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-500">
            No mappings created yet. Fill out the form above to save your first field mapping.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Mapping ID</th>
                  <th className="py-2.5 px-3">Sheet & Source Field</th>
                  <th className="py-2.5 px-3">Target Field</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Version</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sessionMappings.map((m) => (
                  <tr key={m.mapping_id} className="hover:bg-slate-50">
                    <td className="py-2.5 px-3 font-mono text-slate-500">
                      {m.mapping_id.substring(0, 8)}...
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="font-semibold text-slate-900">{m.source_field}</span>
                      <span className="text-slate-400 block text-[10px]">({m.source_sheet})</span>
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-blue-900">
                      {m.target_field}
                      {m.required && <span className="ml-1 text-rose-600">*</span>}
                    </td>
                    <td className="py-2.5 px-3">
                      <Badge variant={m.mapping_type === 'unresolved' ? 'warning' : 'info'}>
                        {m.mapping_type}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3">
                      <Badge variant={m.status === 'approved' ? 'success' : 'neutral'}>
                        {m.status}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3 font-mono">v{m.version}</td>
                    <td className="py-2.5 px-3 text-right space-x-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleViewVersions(m.mapping_id)}
                        icon={<History className="w-3 h-3" />}
                      >
                        History
                      </Button>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => navigate(`/approvals?mappingId=${m.mapping_id}`)}
                        icon={<ExternalLink className="w-3 h-3" />}
                      >
                        Review / Approve
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Version History Modal */}
      <Modal
        isOpen={historyModalOpen}
        onClose={() => setHistoryModalOpen(false)}
        title="Mapping Version History"
      >
        <div className="space-y-3">
          <p className="text-xs text-slate-500">
            Immutable version log for mapping <span className="font-mono">{activeMappingForHistory}</span>.
          </p>

          <div className="divide-y divide-slate-100 max-h-60 overflow-y-auto">
            {versions.map((ver) => (
              <div key={ver.version} className="py-2 text-xs flex items-center justify-between">
                <div>
                  <span className="font-bold text-slate-900">Version {ver.version}</span>
                  <span className="text-slate-400 ml-2">({ver.status})</span>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    {ver.source_field} &rarr; {ver.target_field} ({ver.mapping_type})
                  </div>
                </div>
                <div className="text-right text-[10px] text-slate-400">
                  {new Date(ver.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Modal>
    </div>
  );
};
