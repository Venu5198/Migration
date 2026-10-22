import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BarChart2,
  Calendar,
  CheckCircle,
  ChevronRight,
  FileSpreadsheet,
  Hash,
  Layers,
  Search,
  Upload,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Alert } from '../components/common/Alert';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { Modal } from '../components/common/Modal';
import { SheetSchema, SourceResponse } from '../types';

export const SourcesPage: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Upload State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  // Inspection Modal State
  const [inspectedSource, setInspectedSource] = useState<SourceResponse | null>(null);
  const [selectedSheet, setSelectedSheet] = useState<SheetSchema | null>(null);

  const loadSources = async (pageNumber = 1) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.listSources(pageNumber, 20);
      setSources(res.items);
      setTotal(res.total);
      setPage(res.page);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch uploaded workbooks.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSources(1);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xlsm')) {
      setError('Only Excel workbooks (.xlsx, .xlsm) are supported.');
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      setError('File exceeds maximum upload size (50MB).');
      return;
    }

    setSelectedFile(file);
    setError(null);
    setUploadSuccess(null);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setUploading(true);
    setUploadProgress(0);
    setError(null);
    setUploadSuccess(null);

    try {
      const res = await apiClient.uploadSource(selectedFile, (percent) => {
        setUploadProgress(percent);
      });
      setUploadSuccess(`Successfully uploaded and inventoried "${res.original_filename}" (${res.sheets.length} sheets found).`);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadSources(1);
      handleOpenInspector(res);
    } catch (err: any) {
      setError(err.message || 'Upload failed.');
    } finally {
      setUploading(false);
    }
  };

  const handleOpenInspector = (source: SourceResponse) => {
    setInspectedSource(source);
    setSelectedSheet(source.sheets?.[0] || null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Source Workbooks</h1>
        <p className="text-sm text-slate-500 mt-1">
          Upload and review private source workbooks. Worksheets, headers, and structural findings are parsed on upload.
        </p>
      </div>

      {error && <Alert type="error" onClose={() => setError(null)}>{error}</Alert>}
      {uploadSuccess && <Alert type="success" onClose={() => setUploadSuccess(null)}>{uploadSuccess}</Alert>}

      {/* Upload Box */}
      <Card title="Upload Excel Workbook" subtitle="Upload an .xlsx or .xlsm file (up to 50MB)">
        <div className="flex flex-col md:flex-row gap-4 items-center">
          <div className="flex-1 w-full">
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xlsm"
              onChange={handleFileChange}
              disabled={uploading}
              className="block w-full text-sm text-slate-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-800 hover:file:bg-blue-100 cursor-pointer border border-slate-200 rounded-md p-1"
            />
          </div>

          <Button
            variant="primary"
            disabled={!selectedFile || uploading}
            isLoading={uploading}
            onClick={handleUpload}
            icon={<Upload className="w-4 h-4" />}
          >
            {uploading ? `Uploading (${uploadProgress}%)` : 'Upload & Inventory'}
          </Button>
        </div>

        {uploading && (
          <div className="w-full bg-slate-100 rounded-full h-2 mt-4 overflow-hidden">
            <div
              className="bg-blue-800 h-2 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        )}
      </Card>

      {/* Source Files Table */}
      <Card
        title={`Uploaded Workbooks (${total})`}
        subtitle="Stored securely with SHA-256 verification and sheet inventory"
      >
        {loading ? (
          <div className="py-12 text-center text-sm text-slate-500">Loading workbooks...</div>
        ) : sources.length === 0 ? (
          <EmptyState
            title="No workbooks found"
            description="Upload an Excel workbook above to extract sheets, fields, and validation issues."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-700 text-xs uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="py-3 px-4">Filename</th>
                  <th className="py-3 px-4">Source ID</th>
                  <th className="py-3 px-4">SHA-256 Checksum</th>
                  <th className="py-3 px-4">Worksheets</th>
                  <th className="py-3 px-4">Uploaded At</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-800">
                {sources.map((source) => (
                  <tr key={source.source_id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3 px-4 font-semibold text-slate-900 flex items-center gap-2">
                      <FileSpreadsheet className="w-4 h-4 text-blue-800 shrink-0" />
                      <span>{source.original_filename}</span>
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-slate-500">
                      {source.source_id.substring(0, 8)}...
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-slate-500">
                      {source.sha256.substring(0, 12)}...
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant="navy">
                        {source.sheets?.length || 0} sheets
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-500">
                      {new Date(source.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleOpenInspector(source)}
                      >
                        Inspect Schema
                      </Button>
                      <Button
                        size="sm"
                        variant="primary"
                        icon={<BarChart2 className="w-3.5 h-3.5" />}
                        onClick={() => navigate(`/profiling?sourceId=${source.source_id}`)}
                      >
                        Profile
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Sheet & Header Inspector Modal */}
      <Modal
        isOpen={Boolean(inspectedSource)}
        onClose={() => setInspectedSource(null)}
        title={
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-blue-800" />
            <span>Schema Inspector: {inspectedSource?.original_filename}</span>
          </div>
        }
        maxWidth="4xl"
      >
        {inspectedSource && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-slate-50 p-3 rounded-md text-xs border border-slate-200">
              <div>
                <span className="text-slate-400 block font-medium">Source ID:</span>
                <span className="font-mono text-slate-700">{inspectedSource.source_id}</span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">SHA256 Digest:</span>
                <span className="font-mono text-slate-700 truncate block">
                  {inspectedSource.sha256}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">Discovered Sheets:</span>
                <span className="font-semibold text-slate-900">{inspectedSource.sheets?.length || 0}</span>
              </div>
            </div>

            {/* Sheet Tabs */}
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                Worksheets in Workbook
              </div>
              <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
                {inspectedSource.sheets?.map((sheet) => (
                  <button
                    key={sheet.name}
                    onClick={() => setSelectedSheet(sheet)}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center gap-2 ${
                      selectedSheet?.name === sheet.name
                        ? 'bg-blue-800 text-white font-semibold'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    <Layers className="w-3.5 h-3.5" />
                    <span>{sheet.name}</span>
                    <span className="text-[10px] opacity-80">
                      ({sheet.max_row} rows)
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Selected Sheet Details */}
            {selectedSheet && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                    <span className="text-[11px] text-slate-500 block">Row Count</span>
                    <span className="text-base font-bold text-slate-900">{selectedSheet.max_row}</span>
                  </div>
                  <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                    <span className="text-[11px] text-slate-500 block">Column Count</span>
                    <span className="text-base font-bold text-slate-900">{selectedSheet.max_column}</span>
                  </div>
                  <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                    <span className="text-[11px] text-slate-500 block">Detected Headers</span>
                    <span className="text-base font-bold text-slate-900">{selectedSheet.headers?.length || 0}</span>
                  </div>
                  <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                    <span className="text-[11px] text-slate-500 block">Issues Flagged</span>
                    <span className="text-base font-bold text-rose-700">{selectedSheet.issues?.length || 0}</span>
                  </div>
                </div>

                {/* Validation findings */}
                {selectedSheet.issues && selectedSheet.issues.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-slate-700 uppercase mb-2">
                      Validation Findings on Upload
                    </h4>
                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                      {selectedSheet.issues.map((issue, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900"
                        >
                          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                          <div>
                            <span className="font-semibold mr-1">[{issue.code}]</span>
                            <span>{issue.message}</span>
                            {issue.row && <span className="ml-1 text-slate-500">(Row: {issue.row})</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Headers and inferred types */}
                <div>
                  <h4 className="text-xs font-semibold text-slate-700 uppercase mb-2">
                    Header Columns & Inferred Types
                  </h4>
                  <div className="border border-slate-200 rounded-md overflow-hidden max-h-56 overflow-y-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                        <tr>
                          <th className="py-2 px-3">Column Index</th>
                          <th className="py-2 px-3">Header Name</th>
                          <th className="py-2 px-3">Inferred Type</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {selectedSheet.headers?.map((header, idx) => (
                          <tr key={idx} className="hover:bg-slate-50">
                            <td className="py-2 px-3 text-slate-400 font-mono">#{idx + 1}</td>
                            <td className="py-2 px-3 font-semibold text-slate-900">{header}</td>
                            <td className="py-2 px-3">
                              <Badge variant="info">
                                {selectedSheet.inferred_types?.[header] || 'string'}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="pt-2 flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/mappings?sourceId=${inspectedSource.source_id}&sheet=${selectedSheet.name}`)}
                  >
                    Map This Sheet
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<BarChart2 className="w-3.5 h-3.5" />}
                    onClick={() => navigate(`/profiling?sourceId=${inspectedSource.source_id}`)}
                  >
                    Start Worker Profile
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};
