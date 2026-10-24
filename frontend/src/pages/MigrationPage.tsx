import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Copy,
  Download,
  FileCheck,
  FileSpreadsheet,
  FileText,
  HelpCircle,
  History,
  Info,
  Layers,
  Play,
  PlayCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  StopCircle,
  Upload,
  XCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { JobResponse, SourceResponse } from '../types';

export const MigrationPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Active tab: 'new' | 'details' | 'history'
  const tabParam = searchParams.get('tab') as 'new' | 'details' | 'history' | null;
  const initialJobId = searchParams.get('jobId') || '';
  const [activeTab, setActiveTab] = useState<'new' | 'details' | 'history'>(
    initialJobId ? 'details' : tabParam || 'new'
  );

  // Workflow State: Workbook input
  const [inputMode, setInputMode] = useState<'upload' | 'select'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [availableSources, setAvailableSources] = useState<SourceResponse[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState('');
  const [strategy, setStrategy] = useState<'EMPLOYEE_NUMBER' | 'TOPIA_ID_WITH_FALLBACK'>(
    'EMPLOYEE_NUMBER'
  );

  // Job Details State
  const [currentJobId, setCurrentJobId] = useState<string>(initialJobId);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [jobLoading, setJobLoading] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [copied, setCopied] = useState(false);
  const [downloadingArtifact, setDownloadingArtifact] = useState<string | null>(null);

  // History State
  const [historyJobs, setHistoryJobs] = useState<JobResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historySearch, setHistorySearch] = useState('');

  // Notifications
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Load existing sources for selection
  useEffect(() => {
    const fetchSources = async () => {
      try {
        const res = await apiClient.listSources(1, 50);
        setAvailableSources(res.items);
        if (res.items.length > 0 && !selectedSourceId) {
          setSelectedSourceId(res.items[0].source_id);
        }
      } catch {
        // Soft fail
      }
    };
    fetchSources();
  }, []);

  // Sync tab with URL
  const switchTab = (tab: 'new' | 'details' | 'history', newJobId?: string) => {
    setActiveTab(tab);
    const params = new URLSearchParams(searchParams);
    params.set('tab', tab);
    if (newJobId) {
      params.set('jobId', newJobId);
      setCurrentJobId(newJobId);
    } else if (tab !== 'details') {
      params.delete('jobId');
    }
    setSearchParams(params);
    setError(null);
    setSuccess(null);
  };

  // Poll Job Details
  useEffect(() => {
    if (!currentJobId) return;

    let isMounted = true;
    const fetchCurrentJob = async () => {
      try {
        setJobLoading(true);
        const data = await apiClient.getJob(currentJobId);
        if (isMounted) setJob(data);
      } catch (err: any) {
        if (isMounted) setError(err.message || 'Job was not found.');
      } finally {
        if (isMounted) setJobLoading(false);
      }
    };

    fetchCurrentJob();

    // Set up polling while running
    const interval = setInterval(async () => {
      if (job && ['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'CANCELLED'].includes(job.status)) {
        return;
      }
      try {
        const updated = await apiClient.getJob(currentJobId);
        if (isMounted) setJob(updated);
      } catch {
        // Polling retry
      }
    }, 1500);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [currentJobId, job?.status]);

  // Load History
  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await apiClient.listJobs({ kind: 'equus_migration', page: 1, page_size: 50 });
      setHistoryJobs(res.items);
    } catch (err: any) {
      setError(err.message || 'Failed to load migration history.');
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'history') {
      loadHistory();
    }
  }, [activeTab]);

  // File selection validation
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xlsm')) {
      setError('Unsupported file type. Only Excel workbooks (.xlsx, .xlsm) are supported.');
      setSelectedFile(null);
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      setError('File size exceeds the 50MB maximum upload limit.');
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
    setError(null);
  };

  // Run migration workflow
  const handleStartMigration = async () => {
    setIsSubmitting(true);
    setError(null);
    setSuccess(null);
    setUploadProgress(0);

    try {
      let targetSourceId = selectedSourceId;

      // 1. Upload if uploading a new workbook
      if (inputMode === 'upload') {
        if (!selectedFile) {
          setError('Please select an Excel (.xlsx) file to upload.');
          setIsSubmitting(false);
          return;
        }

        const sourceRes = await apiClient.uploadSource(selectedFile, (pct) => {
          setUploadProgress(pct);
        });
        targetSourceId = sourceRes.source_id;
      } else {
        if (!targetSourceId) {
          setError('Please choose an existing source workbook.');
          setIsSubmitting(false);
          return;
        }
      }

      // 2. Queue Equus Migration Job
      const jobRes = await apiClient.startEquusMigration(targetSourceId, strategy);
      setSuccess(`Migration job queued successfully (ID: ${jobRes.job_id}).`);

      // 3. Clear file inputs & navigate to details tab
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      switchTab('details', jobRes.job_id);
    } catch (err: any) {
      setError(err.message || 'Failed to start migration. Please review workbook format.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Cancel Job
  const handleCancelJob = async () => {
    if (!job) return;
    setCancelling(true);
    try {
      const res = await apiClient.cancelJob(job.job_id);
      setJob(res);
      setSuccess('Job cancellation requested.');
    } catch (err: any) {
      setError(err.message || 'Failed to cancel job.');
    } finally {
      setCancelling(false);
    }
  };

  // Download Artifact
  const handleDownloadArtifact = async (artifactType: 'report' | 'import') => {
    if (!job) return;
    setDownloadingArtifact(artifactType);
    setError(null);
    try {
      const { blob, filename } = await apiClient.downloadArtifact(job.job_id, artifactType);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(link);
      setSuccess(`Downloaded ${filename} successfully.`);
    } catch (err: any) {
      setError(err.message || `Failed to download ${artifactType} artifact.`);
    } finally {
      setDownloadingArtifact(null);
    }
  };

  // Copy Job ID
  const copyJobId = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isTerminal =
    job && ['COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED', 'CANCELLED'].includes(job.status);
  const recon = job?.result?.reconciliation;
  const isReconValid = recon?.is_valid === true;

  // Unified reconciliation counts with fallback resolution
  const sourceRows =
    recon?.source_rows ?? recon?.source_rows_evaluated ?? job?.result?.total_source_rows ?? 0;
  const outputRecords =
    recon?.output_records ?? recon?.total_output_records ?? job?.result?.total_output_records ?? 0;
  const insertRecords =
    recon?.insert_records ?? recon?.insert_records_count ?? job?.result?.insert_records ?? 0;
  const updateRecords =
    recon?.update_records ?? recon?.update_records_count ?? job?.result?.update_records ?? 0;
  const acceptedRecords =
    recon?.accepted_records ?? (isReconValid ? outputRecords : 0);
  const rejectedRecords =
    recon?.rejected_records ?? (!isReconValid ? outputRecords : 0);


  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            <Layers className="w-7 h-7 text-blue-800" />
            Topia to Equus Migration
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Execute shared migration engine directly: parse multi-row headers, transform assignment entities, verify relational reconciliation, and download Equus import workbooks.
          </p>
        </div>

        {/* Tab Navigation Buttons */}
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-xs shrink-0">
          <button
            onClick={() => switchTab('new')}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === 'new'
                ? 'bg-blue-800 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <PlayCircle className="w-3.5 h-3.5" />
            New Migration
          </button>
          <button
            onClick={() => switchTab('details')}
            disabled={!currentJobId}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-colors flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed ${
              activeTab === 'details'
                ? 'bg-blue-800 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileCheck className="w-3.5 h-3.5" />
            Job Details {job && `(${job.status})`}
          </button>
          <button
            onClick={() => switchTab('history')}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === 'history'
                ? 'bg-blue-800 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <History className="w-3.5 h-3.5" />
            Migration History
          </button>
        </div>
      </div>

      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}
      {success && <Alert type="success" onClose={() => setSuccess(null)}>{success}</Alert>}

      {/* 5-Step Client-Friendly Migration Workflow Stepper */}
      <div className="bg-white border border-slate-200 rounded-lg p-3.5 shadow-xs">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-2 border-b border-slate-100 pb-2 mb-2.5">
          <span className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-blue-800" />
            End-to-End Client Migration Lifecycle
          </span>
          <span className="text-[11px] text-slate-500">
            {activeTab === 'new'
              ? 'Stage 1-2: Source Selection & Strategy'
              : activeTab === 'details' && !isTerminal
              ? 'Stage 3: Engine Transformation Running'
              : activeTab === 'details' && isTerminal
              ? 'Stage 4-5: Reconciliation Review & Download'
              : 'Audit & Run History'}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 text-xs">
          <div
            className={`flex items-center gap-2 p-2 rounded-md transition-colors ${
              activeTab === 'new' && !selectedFile
                ? 'bg-blue-50 text-blue-900 font-semibold border border-blue-200'
                : 'text-slate-600'
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-blue-800 text-white flex items-center justify-center text-[10px] shrink-0 font-bold">
              1
            </span>
            <span className="truncate">1. Upload Source</span>
          </div>

          <div
            className={`flex items-center gap-2 p-2 rounded-md transition-colors ${
              activeTab === 'new' && selectedFile
                ? 'bg-blue-50 text-blue-900 font-semibold border border-blue-200'
                : 'text-slate-600'
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-blue-800 text-white flex items-center justify-center text-[10px] shrink-0 font-bold">
              2
            </span>
            <span className="truncate">2. Strategy Selection</span>
          </div>

          <div
            className={`flex items-center gap-2 p-2 rounded-md transition-colors ${
              activeTab === 'details' && !isTerminal
                ? 'bg-blue-50 text-blue-900 font-semibold border border-blue-200'
                : 'text-slate-600'
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-blue-800 text-white flex items-center justify-center text-[10px] shrink-0 font-bold">
              3
            </span>
            <span className="truncate">3. Run Engine</span>
          </div>

          <div
            className={`flex items-center gap-2 p-2 rounded-md transition-colors ${
              activeTab === 'details' && isTerminal
                ? isReconValid
                  ? 'bg-emerald-50 text-emerald-900 font-semibold border border-emerald-200'
                  : 'bg-rose-50 text-rose-900 font-semibold border border-rose-200'
                : 'text-slate-600'
            }`}
          >
            <span
              className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] shrink-0 font-bold text-white ${
                activeTab === 'details' && isTerminal
                  ? isReconValid
                    ? 'bg-emerald-600'
                    : 'bg-rose-600'
                  : 'bg-slate-400'
              }`}
            >
              4
            </span>
            <span className="truncate">4. Inspect Reconciliation</span>
          </div>

          <div
            className={`flex items-center gap-2 p-2 rounded-md transition-colors ${
              activeTab === 'details' && isTerminal
                ? isReconValid
                  ? 'bg-emerald-50 text-emerald-900 font-semibold border border-emerald-200'
                  : 'bg-amber-50 text-amber-900 font-semibold border border-amber-200'
                : 'text-slate-600'
            }`}
          >
            <span
              className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] shrink-0 font-bold text-white ${
                activeTab === 'details' && isTerminal
                  ? isReconValid
                    ? 'bg-emerald-600'
                    : 'bg-amber-600'
                  : 'bg-slate-400'
              }`}
            >
              5
            </span>
            <span className="truncate">5. Download Deliverables</span>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: NEW MIGRATION WORKFLOW */}
      {/* ========================================================================= */}
      {activeTab === 'new' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card
              title="1. Select Topia Export Workbook"
              subtitle="Upload an export workbook or select an already inventoried file"
            >
              {/* Input Mode Selector */}
              <div className="flex gap-4 border-b border-slate-100 pb-4 mb-4">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-800 cursor-pointer">
                  <input
                    type="radio"
                    name="inputMode"
                    value="upload"
                    checked={inputMode === 'upload'}
                    onChange={() => setInputMode('upload')}
                    className="text-blue-800 focus:ring-blue-500"
                  />
                  <span>Upload New .xlsx Workbook</span>
                </label>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-800 cursor-pointer">
                  <input
                    type="radio"
                    name="inputMode"
                    value="select"
                    checked={inputMode === 'select'}
                    onChange={() => setInputMode('select')}
                    className="text-blue-800 focus:ring-blue-500"
                  />
                  <span>Select Inventoried Source</span>
                </label>
              </div>

              {inputMode === 'upload' ? (
                <div className="space-y-4">
                  <div className="border-2 border-dashed border-slate-300 rounded-lg p-6 text-center hover:border-blue-700 transition-colors bg-slate-50/50">
                    <FileSpreadsheet className="w-10 h-10 text-slate-400 mx-auto mb-2" />
                    <p className="text-sm font-medium text-slate-800">
                      Choose Topia Excel export workbook
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      Supports .xlsx or .xlsm (Max 50MB). Contains multi-row header structure.
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".xlsx,.xlsm"
                      onChange={handleFileChange}
                      disabled={isSubmitting}
                      className="hidden"
                      id="migration-file-input"
                    />
                    <label
                      htmlFor="migration-file-input"
                      className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 rounded-md shadow-xs text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                    >
                      <Upload className="w-3.5 h-3.5" />
                      Browse Files
                    </label>
                  </div>

                  {selectedFile && (
                    <div className="flex items-center justify-between p-3 bg-blue-50/60 border border-blue-200 rounded-md text-xs">
                      <div className="flex items-center gap-2.5">
                        <FileSpreadsheet className="w-4 h-4 text-blue-800" />
                        <div>
                          <span className="font-semibold text-slate-900 block">
                            {selectedFile.name}
                          </span>
                          <span className="text-slate-500 text-[11px]">
                            {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                          </span>
                        </div>
                      </div>
                      <Badge variant="navy">Ready to Process</Badge>
                    </div>
                  )}

                  {isSubmitting && uploadProgress > 0 && uploadProgress < 100 && (
                    <div>
                      <div className="flex justify-between text-xs text-slate-600 mb-1">
                        <span>Uploading workbook...</span>
                        <span>{uploadProgress}%</span>
                      </div>
                      <div className="w-full bg-slate-200 rounded-full h-2">
                        <div
                          className="bg-blue-800 h-2 rounded-full transition-all duration-200"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <label className="block text-xs font-semibold text-slate-700">
                    Inventoried Sources ({availableSources.length})
                  </label>
                  {availableSources.length === 0 ? (
                    <p className="text-xs text-slate-500 py-4 text-center">
                      No sources inventoried yet. Please upload a workbook above.
                    </p>
                  ) : (
                    <select
                      value={selectedSourceId}
                      onChange={(e) => setSelectedSourceId(e.target.value)}
                      disabled={isSubmitting}
                      className="w-full text-sm px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white"
                    >
                      {availableSources.map((s) => (
                        <option key={s.source_id} value={s.source_id}>
                          {s.original_filename} ({new Date(s.created_at).toLocaleDateString()})
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}
            </Card>

            {/* Migration Strategy Selection */}
            <Card
              title="2. Assignment Identifier Strategy"
              subtitle="Select how primary and secondary identifiers are mapped to Equus import columns"
            >
              <div className="space-y-3">
                <label
                  className={`flex items-start gap-3 p-3.5 rounded-lg border cursor-pointer transition-all ${
                    strategy === 'EMPLOYEE_NUMBER'
                      ? 'border-blue-600 bg-blue-50/40 ring-1 ring-blue-600'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <input
                    type="radio"
                    name="strategy"
                    value="EMPLOYEE_NUMBER"
                    checked={strategy === 'EMPLOYEE_NUMBER'}
                    onChange={() => setStrategy('EMPLOYEE_NUMBER')}
                    className="mt-1 text-blue-800 focus:ring-blue-500"
                  />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-900">
                        Option B: Normalized Employee Number in Assignment ID
                      </span>
                      <Badge variant="success">Recommended</Badge>
                    </div>
                    <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                      Target Assignment ID receives normalized <strong>Employee Number</strong> (`EMP-1001-A1`, `EMP-1001-A2`). Topia Assignment ID is preserved into Equus custom field <code>ASSIGNMENT_CF!CF_TEXT029</code>.
                    </p>
                    <div className="mt-2.5 p-2.5 bg-slate-50 border border-slate-200 rounded text-[11px] text-slate-700 space-y-1">
                      <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                        <Info className="w-3.5 h-3.5 text-blue-800" />
                        Concrete Synthetic Example:
                      </div>
                      <div className="font-mono text-[10.5px] text-slate-800 pl-5">
                        • Primary INSERT (Row 4): Col 5 (Assignment ID) = <span className="font-bold text-emerald-700">EMP-1001-A1</span>, Col 29 (Topia ID) = <span className="font-bold text-blue-700">TOP-5001</span>
                      </div>
                      <div className="font-mono text-[10.5px] text-slate-800 pl-5">
                        • Secondary UPDATE (Row 5+): Col 5 (Parent Key) = <span className="font-bold text-emerald-700">EMP-1001-A1</span>, Col 3 (Employee Number) = <span className="text-slate-400">blank</span>
                      </div>
                      <div className="text-[10px] text-slate-500 pl-5">
                        Eliminates identifier collisions across runs and guarantees deterministic parent-child linkage.
                      </div>
                    </div>
                  </div>
                </label>

                <label
                  className={`flex items-start gap-3 p-3.5 rounded-lg border cursor-pointer transition-all ${
                    strategy === 'TOPIA_ID_WITH_FALLBACK'
                      ? 'border-blue-600 bg-blue-50/40 ring-1 ring-blue-600'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <input
                    type="radio"
                    name="strategy"
                    value="TOPIA_ID_WITH_FALLBACK"
                    checked={strategy === 'TOPIA_ID_WITH_FALLBACK'}
                    onChange={() => setStrategy('TOPIA_ID_WITH_FALLBACK')}
                    className="mt-1 text-blue-800 focus:ring-blue-500"
                  />
                  <div>
                    <span className="text-sm font-semibold text-slate-900">
                      Option A: Topia Assignment ID with Fallback
                    </span>
                    <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                      Target Assignment ID receives <strong>Topia Assignment ID</strong> directly (`TOP-5001`), falling back to normalized Employee Number only if absent in source export.
                    </p>
                    <div className="mt-2.5 p-2.5 bg-slate-50 border border-slate-200 rounded text-[11px] text-slate-700 space-y-1">
                      <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                        <Info className="w-3.5 h-3.5 text-blue-800" />
                        Concrete Synthetic Example:
                      </div>
                      <div className="font-mono text-[10.5px] text-slate-800 pl-5">
                        • Primary INSERT (Row 4): Col 5 (Assignment ID) = <span className="font-bold text-blue-700">TOP-5001</span> (from source Topia ID)
                      </div>
                      <div className="font-mono text-[10.5px] text-slate-800 pl-5">
                        • Secondary UPDATE (Row 5+): Col 5 (Parent Key) = <span className="font-bold text-blue-700">TOP-5001</span>
                      </div>
                      <div className="text-[10px] text-slate-500 pl-5">
                        Preserves legacy Topia IDs directly; relies on client confirming Topia ID uniqueness across all employees.
                      </div>
                    </div>
                  </div>
                </label>
              </div>
            </Card>

            {/* Run Button Card */}
            <div className="flex items-center justify-between p-4 bg-white border border-slate-200 rounded-lg shadow-xs">
              <div className="text-xs text-slate-500">
                Processed asynchronously by the migration worker pipeline.
              </div>
              <Button
                variant="primary"
                size="lg"
                isLoading={isSubmitting}
                disabled={isSubmitting || (inputMode === 'upload' && !selectedFile)}
                onClick={handleStartMigration}
                icon={<Play className="w-4 h-4 fill-current" />}
              >
                {isSubmitting ? 'Starting Migration...' : 'Run Equus Migration'}
              </Button>
            </div>
          </div>

          {/* Right Info Rail */}
          <div className="space-y-6">
            <Card title="Migration Pipeline Guardrails">
              <div className="space-y-4 text-xs text-slate-600">
                <div className="flex items-start gap-2.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-slate-900 block">Strict Overwrite Guard</span>
                    <span>Existing output workbooks and mapping reports are protected from overwriting.</span>
                  </div>
                </div>
                <div className="flex items-start gap-2.5">
                  <FileCheck className="w-4 h-4 text-blue-800 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-slate-900 block">3-Row Parity Engine</span>
                    <span>Reads technical names, row-1 rules, and data rows deterministically.</span>
                  </div>
                </div>
                <div className="flex items-start gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-slate-900 block">Relational Integrity</span>
                    <span>Verifies 1 INSERT per assignment plus required UPDATE rows.</span>
                  </div>
                </div>
              </div>
            </Card>

            <Card title="Quick CLI Alternative">
              <p className="text-xs text-slate-500 leading-relaxed mb-3">
                Need to process files directly from PowerShell without starting the UI?
              </p>
              <pre className="p-3 bg-slate-900 text-slate-100 rounded text-[11px] font-mono overflow-x-auto">
                python local/run_local.py
              </pre>
            </Card>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: JOB DETAILS & RECONCILIATION */}
      {/* ========================================================================= */}
      {activeTab === 'details' && (
        <div className="space-y-6">
          {!currentJobId ? (
            <Card>
              <EmptyState
                title="No Migration Job Selected"
                description="Start a new migration or select a job from history to inspect results."
                action={
                  <Button variant="primary" onClick={() => switchTab('new')}>
                    Start New Migration
                  </Button>
                }
              />
            </Card>
          ) : jobLoading && !job ? (
            <Card>
              <div className="py-12 text-center text-sm text-slate-500">
                Loading migration job details...
              </div>
            </Card>
          ) : !job ? (
            <Card>
              <EmptyState
                title="Job Not Found"
                description={`Unable to locate job with identifier: ${currentJobId}`}
                action={
                  <Button variant="outline" onClick={() => switchTab('history')}>
                    View Migration History
                  </Button>
                }
              />
            </Card>
          ) : (
            <>
              {/* Header Card */}
              <Card
                title={
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-lg font-bold text-slate-900">
                      Migration Job Details
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

                    {/* Distinct Reconciliation Badge */}
                    {recon && (
                      <Badge variant={isReconValid ? 'success' : 'danger'}>
                        Reconciliation: {isReconValid ? 'PASSED' : 'FAILED'}
                      </Badge>
                    )}
                  </div>
                }
                subtitle={`Job UUID: ${job.job_id}`}
                action={
                  <div className="flex items-center gap-2">
                    {!isTerminal && (
                      <Button
                        variant="danger"
                        size="sm"
                        isLoading={cancelling}
                        onClick={handleCancelJob}
                        icon={<StopCircle className="w-3.5 h-3.5" />}
                      >
                        Cancel Job
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setJobLoading(true);
                        apiClient.getJob(job.job_id).then(setJob).finally(() => setJobLoading(false));
                      }}
                      icon={<RefreshCw className={`w-3.5 h-3.5 ${jobLoading ? 'animate-spin' : ''}`} />}
                    >
                      Refresh
                    </Button>
                  </div>
                }
              >
                {/* Metadata Row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-slate-50 p-4 rounded-lg border border-slate-200 text-xs">
                  <div className="min-w-0">
                    <span className="text-slate-400 block font-medium">Job Identifier</span>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="font-mono text-slate-800 text-[11px] truncate">{job.job_id}</span>
                      <button
                        onClick={() => copyJobId(job.job_id)}
                        className="text-slate-400 hover:text-slate-600 transition-colors shrink-0"
                        title="Copy Job ID"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                      {copied && <span className="text-[10px] text-emerald-600 font-medium">Copied!</span>}
                    </div>
                  </div>
                  <div className="min-w-0">
                    <span className="text-slate-400 block font-medium">Source Workbook</span>
                    <span
                      className="font-semibold text-slate-800 truncate block"
                      title={job.source_filename || job.result?.source_name || job.source_id}
                    >
                      {job.source_filename || job.result?.source_name || job.source_id.substring(0, 12)}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <span className="text-slate-400 block font-medium">Strategy</span>
                    <span className="font-semibold text-slate-800 truncate block">
                      {job.result?.reconciliation?.assignment_id_strategy || job.strategy || 'Default'}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <span className="text-slate-400 block font-medium">Created / Updated</span>
                    <span className="text-slate-700 truncate block">
                      {new Date(job.created_at).toLocaleTimeString()} ({job.attempts} attempt{job.attempts !== 1 ? 's' : ''})
                    </span>
                  </div>
                </div>
              </Card>

              {/* Status Alert if not completed */}
              {!isTerminal && (
                <div className="flex items-center gap-3 p-4 bg-sky-50 border border-sky-200 rounded-lg text-sky-800 text-sm">
                  <RefreshCw className="w-5 h-5 animate-spin shrink-0 text-sky-600" />
                  <div>
                    <span className="font-semibold block">Migration Engine Processing</span>
                    <span className="text-xs text-sky-700">
                      Transforming assignments, generating Equus import artifacts, and verifying reconciliation. Polling status automatically...
                    </span>
                  </div>
                </div>
              )}

              {/* Results & Reconciliation View */}
              {job.result && (
                <div className="space-y-6">
                  {/* Reconciliation Banner: Clearly distinguishes validation from execution */}
                  <div
                    className={`p-4 rounded-lg border flex items-start gap-3.5 ${
                      isReconValid
                        ? 'bg-emerald-50/80 border-emerald-300 text-emerald-900'
                        : 'bg-rose-50/80 border-rose-300 text-rose-900'
                    }`}
                  >
                    {isReconValid ? (
                      <CheckCircle2 className="w-6 h-6 text-emerald-600 shrink-0 mt-0.5" />
                    ) : (
                      <AlertTriangle className="w-6 h-6 text-rose-600 shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <h3 className="font-bold text-sm">
                            {isReconValid
                              ? 'Reconciliation Validation: PASSED'
                              : 'Reconciliation Validation: FAILED'}
                          </h3>
                          <div
                            className={`text-xs font-semibold mt-0.5 ${
                              isReconValid ? 'text-emerald-800' : 'text-rose-800'
                            }`}
                          >
                            {isReconValid
                              ? 'Approved for Downstream Import'
                              : 'Not Approved for Import (Diagnostic Review Only)'}
                          </div>
                        </div>
                        <Badge variant={isReconValid ? 'success' : 'danger'}>
                          {isReconValid ? 'APPROVED FOR IMPORT' : 'DIAGNOSTIC REVIEW ONLY'}
                        </Badge>
                      </div>
                      <p className="text-xs mt-1 opacity-90 leading-relaxed">
                        {isReconValid
                          ? 'All relational integrity constraints verified. 1 INSERT row per assignment with populated Employee Number and Assignment Identifier. All UPDATE rows reference valid parent keys.'
                          : 'Relational integrity errors detected. The transformation engine generated output rows, but the workbook failed validation constraints. This output is strictly for offline diagnostic review and must NOT be imported into Equus.'}
                      </p>

                      {/* Summary alert when reconciliation fails */}
                      {!isReconValid && recon?.errors && recon.errors.length > 0 && (
                        <div className="mt-3 p-2.5 bg-white/85 border border-rose-200 rounded text-xs text-rose-950 flex items-center justify-between gap-2">
                          <span className="font-semibold text-[11.5px] text-rose-800 flex items-center gap-1.5">
                            <XCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                            {recon.errors.length} Required-Field Failure{recon.errors.length > 1 ? 's' : ''} Detected (See Reconciliation Audit Details below)
                          </span>
                          <span className="text-[10px] uppercase font-bold text-rose-700 bg-rose-100 px-2 py-0.5 rounded shrink-0">
                            Import Blocked
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Metrics Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <Card className="border-l-4 border-l-blue-800">
                      <div className="text-xs font-semibold text-slate-500 uppercase">
                        Source Rows
                      </div>
                      <div className="text-2xl font-bold text-slate-900 mt-1">
                        {sourceRows}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">Evaluated assignment rows</div>
                    </Card>

                    <Card className={`border-l-4 ${isReconValid ? 'border-l-emerald-600' : 'border-l-amber-600'}`}>
                      <div className="text-xs font-semibold text-slate-500 uppercase">
                        Output Records
                      </div>
                      <div className="text-2xl font-bold text-slate-900 mt-1">
                        {outputRecords}
                      </div>
                      <div className="text-xs text-slate-600 font-medium mt-0.5">
                        {insertRecords} INSERT / {updateRecords} UPDATE
                      </div>
                      <div className="text-[11px] font-semibold mt-1">
                        {isReconValid ? (
                          <span className="text-emerald-700">{acceptedRecords} Accepted for Import</span>
                        ) : (
                          <span className="text-rose-700">{rejectedRecords} Rejected (Diagnostic Only)</span>
                        )}
                      </div>
                    </Card>

                    <Card className="border-l-4 border-l-indigo-600">
                      <div className="text-xs font-semibold text-slate-500 uppercase">
                        Mapping Coverage
                      </div>
                      <div className="text-2xl font-bold text-slate-900 mt-1">
                        {(job.result.coverage_percentage ?? 0).toFixed(1)}%
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-1.5 mt-2">
                        <div
                          className="bg-indigo-600 h-1.5 rounded-full"
                          style={{ width: `${Math.min(100, job.result.coverage_percentage || 0)}%` }}
                        />
                      </div>
                    </Card>

                    <Card
                      className={`border-l-4 ${
                        isReconValid ? 'border-l-emerald-600' : 'border-l-rose-600'
                      }`}
                    >
                      <div className="text-xs font-semibold text-slate-500 uppercase">
                        Reconciliation Status
                      </div>
                      <div
                        className={`text-xl font-bold mt-1 ${
                          isReconValid ? 'text-emerald-700' : 'text-rose-700'
                        }`}
                      >
                        {isReconValid ? 'PASSED' : 'FAILED'}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {recon?.errors?.length || 0} errors · {job.result.warnings_count ?? (recon?.warnings?.length || 0)} warnings
                      </div>
                    </Card>
                  </div>

                  {/* Equus Template Coverage & Field Mapping Breakdown Card */}
                  <Card
                    title="Equus Template Coverage & Field Breakdown"
                    subtitle="Detailed explanation of the 146-column bundled Equus EAFH template mapping"
                  >
                    <div className="space-y-4">
                      {/* Grid of Column Counts */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-3.5 rounded-lg border border-slate-200 text-xs">
                        <div>
                          <span className="text-slate-500 block font-medium">Equus Template Target Cols</span>
                          <span className="text-lg font-bold text-slate-900 mt-0.5 block">146</span>
                          <span className="text-[11px] text-slate-400">Cols A through EP</span>
                        </div>
                        <div>
                          <span className="text-slate-500 block font-medium">Mapped Target Columns</span>
                          <span className="text-lg font-bold text-emerald-700 mt-0.5 block">
                            {job.result.mapped_columns_count ??
                              Math.round(((job.result.coverage_percentage || 0) / 100) * 146)}
                          </span>
                          <span className="text-[11px] text-slate-400">Populated from Topia</span>
                        </div>
                        <div>
                          <span className="text-slate-500 block font-medium">Unmapped Columns</span>
                          <span className="text-lg font-bold text-slate-600 mt-0.5 block">
                            {job.result.unmapped_columns_count ??
                              146 -
                                (job.result.mapped_columns_count ??
                                  Math.round(((job.result.coverage_percentage || 0) / 100) * 146))}
                          </span>
                          <span className="text-[11px] text-slate-400">Not present in source</span>
                        </div>
                        <div>
                          <span className="text-slate-500 block font-medium">Calculated Coverage</span>
                          <span className="text-lg font-bold text-indigo-700 mt-0.5 block">
                            {(job.result.coverage_percentage ?? 0).toFixed(2)}%
                          </span>
                          <span className="text-[11px] text-slate-400">Mapped / 146 total</span>
                        </div>
                      </div>

                      {/* Formula & Explanation Box */}
                      <div className="p-3.5 bg-blue-50/60 border border-blue-200 rounded-lg text-xs space-y-2.5">
                        <div className="font-semibold text-blue-900 flex items-center gap-1.5">
                          <HelpCircle className="w-4 h-4 text-blue-800" />
                          Coverage Definition, Classification & Structural Semantics:
                        </div>
                        <div className="font-mono text-[11px] text-blue-950 pl-5 bg-white/70 p-2 rounded border border-blue-100">
                          Field Coverage (%) = (Mapped Target Columns ÷ 146 Total Equus Columns) × 100
                        </div>
                        <div className="space-y-1.5 text-slate-600 text-[11.5px] leading-relaxed pl-5">
                          <p>
                            <strong>Structural Mapping Metric:</strong> Coverage measures structural schema mapping completeness between the source sheet and the 146 standard Equus EAFH columns (Columns A–EP). It is <em>not</em> proof of successful migration or data quality (a workbook with 100% column coverage can still fail validation if required fields are missing).
                          </p>
                          <p>
                            <strong>Field Classification:</strong>
                            <br />• <strong>Required Core Fields (5):</strong> Employee Command (Col 1), Assignment Command (Col 2), Employee Number (Col 3), Assignment Number (Col 4), Assignment Identifier (Col 5). Required for every INSERT record.
                            <br />• <strong>Mapped Fields ({job.result.mapped_columns_count ?? 11}):</strong> Demographic, date, location, ISO-3 country, and dropdown fields translated from Topia.
                            <br />• <strong>Unmapped Columns ({job.result.unmapped_columns_count ?? 135}):</strong> Target columns in the bundled 146-column template not supplied in this export. Unmapped columns include client-specific custom fields (<code>CF_TEXT...</code>), compensation, and optional modules. (Unmapped fields are not all guaranteed optional unless established by the client's Equus configuration).
                          </p>
                        </div>
                      </div>
                    </div>
                  </Card>


                  {/* Artifact Downloads Section */}
                  <Card
                    title="Generated Migration Artifacts"
                    subtitle="Download official Equus import workbook and mapping report"
                  >
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {/* Equus Import / Diagnostic File */}
                      <div
                        className={`p-4 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-4 min-w-0 ${
                          isReconValid
                            ? 'border-emerald-200 bg-emerald-50/30'
                            : 'border-rose-200 bg-rose-50/30'
                        }`}
                      >
                        <div className="flex items-start sm:items-center gap-3 min-w-0">
                          <div
                            className={`p-2.5 rounded-lg shrink-0 ${
                              isReconValid
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            <FileSpreadsheet className="w-5 h-5" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-semibold text-slate-900 truncate">
                                {isReconValid
                                  ? 'Equus Migration Workbook'
                                  : 'Equus Diagnostic File (Unapproved)'}
                              </span>
                              <Badge variant={isReconValid ? 'success' : 'danger'}>
                                {isReconValid ? 'APPROVED FOR IMPORT' : 'DIAGNOSTIC ONLY'}
                              </Badge>
                            </div>
                            <div
                              className="text-xs text-slate-500 font-mono mt-0.5 break-all sm:truncate"
                              title={job.result.import_file || ''}
                            >
                              {job.result.import_file || 'Ready for download'}
                            </div>
                            <div className="text-[11px] text-slate-500 mt-1">
                              {isReconValid
                                ? 'Validated & verified: Safe for production Equus EAFH import.'
                                : 'Caution: Failed reconciliation. For offline diagnostic review only. Do not import.'}
                            </div>
                          </div>
                        </div>

                        <Button
                          variant={isReconValid ? 'primary' : 'outline'}
                          size="sm"
                          className="w-full sm:w-auto shrink-0"
                          isLoading={downloadingArtifact === 'import'}
                          disabled={Boolean(downloadingArtifact)}
                          onClick={() => handleDownloadArtifact('import')}
                          icon={<Download className="w-3.5 h-3.5" />}
                        >
                          {isReconValid ? 'Download Equus (.xlsx)' : 'Download Diagnostic File (.xlsx)'}
                        </Button>
                      </div>

                      {/* Mapping Report File */}
                      <div className="p-4 rounded-lg border border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4 min-w-0">
                        <div className="flex items-start sm:items-center gap-3 min-w-0">
                          <div className="p-2.5 bg-blue-100 text-blue-800 rounded-lg shrink-0">
                            <FileText className="w-5 h-5" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-semibold text-slate-900 truncate">
                                Migration Results (Audit Report)
                              </span>
                              <Badge variant="navy">AUDIT REPORT</Badge>
                            </div>
                            <div
                              className="text-xs text-slate-500 font-mono mt-0.5 break-all sm:truncate"
                              title={job.result.report_file || ''}
                            >
                              {job.result.report_file || 'Ready for download'}
                            </div>
                            <div className="text-[11px] text-slate-500 mt-1">
                              Contains 4 tabs: Summary, Column Mappings, Translations, Warnings.
                            </div>
                          </div>
                        </div>

                        <Button
                          variant="outline"
                          size="sm"
                          className="w-full sm:w-auto shrink-0"
                          isLoading={downloadingArtifact === 'report'}
                          disabled={Boolean(downloadingArtifact)}
                          onClick={() => handleDownloadArtifact('report')}
                          icon={<Download className="w-3.5 h-3.5" />}
                        >
                          Download Migration Results
                        </Button>
                      </div>
                    </div>
                  </Card>

                  {/* Reconciliation Errors / Warnings Details */}
                  {recon && (
                    <Card
                      title="Reconciliation Audit Details"
                      subtitle="Field-level relational integrity breakdown"
                    >
                      <div className="space-y-4">
                        {/* Errors */}
                        {recon.errors && recon.errors.length > 0 && (
                          <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg">
                            <h4 className="text-xs font-bold uppercase tracking-wider text-rose-800 flex items-center gap-1.5 mb-2">
                              <XCircle className="w-4 h-4" />
                              Validation Errors ({recon.errors.length})
                            </h4>
                            <ul className="list-disc list-inside text-xs text-rose-900 space-y-1">
                              {recon.errors.map((err: string, i: number) => (
                                <li key={i}>{err}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Warnings */}
                        {recon.warnings && recon.warnings.length > 0 && (
                          <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                            <h4 className="text-xs font-bold uppercase tracking-wider text-amber-800 flex items-center gap-1.5 mb-2">
                              <AlertCircle className="w-4 h-4" />
                              Warnings ({recon.warnings.length})
                            </h4>
                            <ul className="list-disc list-inside text-xs text-amber-900 space-y-1 max-h-48 overflow-y-auto">
                              {recon.warnings.map((warn: string, i: number) => (
                                <li key={i}>{warn}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Relational Summary Table */}
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs text-left">
                            <thead className="bg-slate-100 text-slate-700 uppercase font-semibold">
                              <tr>
                                <th className="p-2.5">Check / Constraint</th>
                                <th className="p-2.5">Count / Value</th>
                                <th className="p-2.5">Status</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 text-slate-800">
                              <tr>
                                <td className="p-2.5 font-medium">Source Evaluated Rows</td>
                                <td className="p-2.5">{sourceRows}</td>
                                <td className="p-2.5"><Badge variant="neutral">Verified</Badge></td>
                              </tr>
                              <tr>
                                <td className="p-2.5 font-medium">Generated Output Records</td>
                                <td className="p-2.5">{outputRecords}</td>
                                <td className="p-2.5"><Badge variant="neutral">Attempted</Badge></td>
                              </tr>
                              <tr>
                                <td className="p-2.5 font-medium">1 INSERT Row per Assignment</td>
                                <td className="p-2.5">{insertRecords}</td>
                                <td className="p-2.5">
                                  <Badge variant={insertRecords === sourceRows && insertRecords > 0 ? 'success' : 'warning'}>
                                    {insertRecords === sourceRows && insertRecords > 0 ? 'Balanced' : 'Discrepancy'}
                                  </Badge>
                                </td>
                              </tr>
                              <tr>
                                <td className="p-2.5 font-medium">Secondary UPDATE Records</td>
                                <td className="p-2.5">{updateRecords}</td>
                                <td className="p-2.5"><Badge variant="neutral">Related Entities</Badge></td>
                              </tr>
                              <tr>
                                <td className="p-2.5 font-medium">Accepted Import Records</td>
                                <td className="p-2.5 font-semibold text-emerald-700">{acceptedRecords}</td>
                                <td className="p-2.5">
                                  <Badge variant={isReconValid ? 'success' : 'neutral'}>
                                    {isReconValid ? 'Approved for Import' : 'None'}
                                  </Badge>
                                </td>
                              </tr>
                              <tr>
                                <td className="p-2.5 font-medium">Rejected / Diagnostic Records</td>
                                <td className="p-2.5 font-semibold text-rose-700">{rejectedRecords}</td>
                                <td className="p-2.5">
                                  <Badge variant={!isReconValid ? 'danger' : 'neutral'}>
                                    {!isReconValid ? 'Import Blocked' : 'None'}
                                  </Badge>
                                </td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </Card>
                  )}

                </div>
              )}

              {/* Failure Code */}
              {job.failure_code && (
                <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-sm">
                  <span className="font-semibold block">Execution Error: {job.failure_code}</span>
                  <span className="text-xs">
                    The migration worker encountered an unexpected error processing this workbook. Please verify the source structure.
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: MIGRATION HISTORY */}
      {/* ========================================================================= */}
      {activeTab === 'history' && (
        <Card
          title="Topia to Equus Migration History"
          subtitle="Audit trail of all executed migration runs and generated artifacts"
          action={
            <Button
              size="sm"
              variant="outline"
              onClick={loadHistory}
              isLoading={historyLoading}
              icon={<RefreshCw className={`w-3.5 h-3.5 ${historyLoading ? 'animate-spin' : ''}`} />}
            >
              Refresh
            </Button>
          }
        >
          {/* Search bar */}
          <div className="mb-4">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                value={historySearch}
                onChange={(e) => setHistorySearch(e.target.value)}
                placeholder="Filter by filename or Job UUID..."
                className="w-full text-xs pl-9 pr-4 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>
          </div>

          {historyLoading && historyJobs.length === 0 ? (
            <div className="py-12 text-center text-sm text-slate-500">
              Loading migration history...
            </div>
          ) : historyJobs.length === 0 ? (
            <EmptyState
              title="No Migration Runs Recorded"
              description="No Topia-to-Equus migration jobs have been executed yet."
              action={
                <Button variant="primary" onClick={() => switchTab('new')}>
                  Start First Migration
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-700 uppercase font-semibold border-b border-slate-200">
                  <tr>
                    <th className="py-3 px-3">Job ID</th>
                    <th className="py-3 px-3">Source Workbook</th>
                    <th className="py-3 px-3">Created</th>
                    <th className="py-3 px-3">Execution</th>
                    <th className="py-3 px-3">Reconciliation</th>
                    <th className="py-3 px-3">Coverage</th>
                    <th className="py-3 px-3">Outputs</th>
                    <th className="py-3 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-800">
                  {historyJobs
                    .filter((j) => {
                      if (!historySearch.trim()) return true;
                      const q = historySearch.toLowerCase();
                      const name = (j.source_filename || j.result?.source_name || '').toLowerCase();
                      return name.includes(q) || j.job_id.toLowerCase().includes(q);
                    })
                    .map((item) => {
                      const itemRecon = item.result?.reconciliation;
                      const itemReconValid = itemRecon?.is_valid === true;

                      return (
                        <tr key={item.job_id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-3 px-3 font-mono text-[11px] text-slate-600">
                            {item.job_id.substring(0, 8)}...
                          </td>
                          <td
                            className="py-3 px-3 font-semibold text-slate-900 max-w-xs truncate"
                            title={item.source_filename || item.result?.source_name || ''}
                          >
                            {item.source_filename || item.result?.source_name || 'Topia Export'}
                          </td>
                          <td className="py-3 px-3 text-slate-500">
                            {new Date(item.created_at).toLocaleString()}
                          </td>
                          <td className="py-3 px-3">
                            <Badge
                              variant={
                                item.status === 'COMPLETED'
                                  ? 'success'
                                  : item.status === 'COMPLETED_WITH_ERRORS'
                                  ? 'warning'
                                  : item.status === 'FAILED'
                                  ? 'danger'
                                  : 'navy'
                              }
                            >
                              {item.status}
                            </Badge>
                          </td>
                          <td className="py-3 px-3">
                            {itemRecon ? (
                              <Badge variant={itemReconValid ? 'success' : 'danger'}>
                                {itemReconValid ? 'PASSED' : 'FAILED'}
                              </Badge>
                            ) : (
                              <span className="text-slate-400">N/A</span>
                            )}
                          </td>
                          <td className="py-3 px-3 font-medium">
                            {item.result?.coverage_percentage !== undefined
                              ? `${item.result.coverage_percentage.toFixed(1)}%`
                              : '-'}
                          </td>
                          <td className="py-3 px-3 text-slate-600">
                            {item.result?.total_output_records !== undefined
                              ? `${item.result.total_output_records} records`
                              : '-'}
                          </td>
                          <td className="py-3 px-3 text-right space-x-1.5">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => switchTab('details', item.job_id)}
                            >
                              Inspect Details
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};
