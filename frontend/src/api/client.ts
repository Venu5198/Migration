import axios, { AxiosError, AxiosProgressEvent } from 'axios';
import {
  AuditEvent,
  HealthResponse,
  JobResponse,
  MappingCreate,
  MappingResponse,
  MappingUpdate,
  PagedAuditEvents,
  PagedSources,
  ReconciliationReport,
  SheetSchema,
  SourceResponse,
  TargetConnectionResponse,
} from '../types';

export class ApiError extends Error {
  code: string;
  status: number;
  data?: any;

  constructor(message: string, code = 'UNKNOWN_ERROR', status = 500, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.data = data;
  }
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: {
    'Accept': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('migration_auth_token') || sessionStorage.getItem('migration_auth_token');
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<any>) => {
    const status = error.response?.status || 500;
    const responseData = error.response?.data;

    let code = 'NETWORK_ERROR';
    let message = error.message;

    if (responseData) {
      if (typeof responseData === 'object') {
        if (responseData.error && typeof responseData.error === 'object') {
          code = responseData.error.code || 'DOMAIN_ERROR';
          message = responseData.error.message || message;
        } else if (responseData.detail) {
          if (typeof responseData.detail === 'object') {
            code = responseData.detail.code || 'API_ERROR';
            message = responseData.detail.message || message;
          } else if (typeof responseData.detail === 'string') {
            message = responseData.detail;
            code = status === 401 ? 'UNAUTHENTICATED' : status === 403 ? 'FORBIDDEN' : 'API_ERROR';
          }
        }
      }
    }

    return Promise.reject(new ApiError(message, code, status, responseData));
  }
);

export const apiClient = {
  // System Health
  async getHealth(): Promise<HealthResponse> {
    const res = await api.get<HealthResponse>('/health');
    return res.data;
  },

  async getReady(): Promise<{ status: string; database: string }> {
    const res = await api.get<{ status: string; database: string }>('/ready');
    return res.data;
  },

  async getLive(): Promise<{ status: string }> {
    const res = await api.get<{ status: string }>('/live');
    return res.data;
  },

  // Sources
  async uploadSource(
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<SourceResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const res = await api.post<SourceResponse>('/api/v1/sources/upload', formData, {
      onUploadProgress: (progressEvent: AxiosProgressEvent) => {
        if (progressEvent.total && onProgress) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    return res.data;
  },

  async listSources(page = 1, pageSize = 50): Promise<PagedSources> {
    const res = await api.get<PagedSources>('/api/v1/sources', {
      params: { page, page_size: pageSize },
    });
    return res.data;
  },

  async getSource(sourceId: string): Promise<SourceResponse> {
    const res = await api.get<SourceResponse>(`/api/v1/sources/${sourceId}`);
    return res.data;
  },

  async getSourceSheets(sourceId: string): Promise<SheetSchema[]> {
    const res = await api.get<SheetSchema[]>(`/api/v1/sources/${sourceId}/sheets`);
    return res.data;
  },

  // Jobs
  async startProfileJob(sourceId: string): Promise<JobResponse> {
    const res = await api.post<JobResponse>(`/api/v1/sources/${sourceId}/profile`);
    return res.data;
  },

  async startPreviewJob(sourceId: string, mappingId: string): Promise<JobResponse> {
    const res = await api.post<JobResponse>('/api/v1/migrations/preview', {
      source_id: sourceId,
      mapping_id: mappingId,
    });
    return res.data;
  },

  async getJob(jobId: string): Promise<JobResponse> {
    const res = await api.get<JobResponse>(`/api/v1/jobs/${jobId}`);
    return res.data;
  },

  async cancelJob(jobId: string): Promise<JobResponse> {
    const res = await api.post<JobResponse>(`/api/v1/jobs/${jobId}/cancel`);
    return res.data;
  },

  // Mappings
  async createMapping(payload: MappingCreate): Promise<MappingResponse> {
    const res = await api.post<MappingResponse>('/api/v1/mappings', payload);
    return res.data;
  },

  async getMapping(mappingId: string): Promise<MappingResponse> {
    const res = await api.get<MappingResponse>(`/api/v1/mappings/${mappingId}`);
    return res.data;
  },

  async updateMapping(mappingId: string, payload: MappingUpdate): Promise<MappingResponse> {
    const res = await api.put<MappingResponse>(`/api/v1/mappings/${mappingId}`, payload);
    return res.data;
  },

  async getMappingVersions(mappingId: string): Promise<MappingResponse[]> {
    const res = await api.get<MappingResponse[]>(`/api/v1/mappings/${mappingId}/versions`);
    return res.data;
  },

  async approveMapping(mappingId: string): Promise<MappingResponse> {
    const res = await api.post<MappingResponse>(`/api/v1/mappings/${mappingId}/approve`);
    return res.data;
  },

  // Reports
  async getReconciliation(jobId: string): Promise<ReconciliationReport> {
    const res = await api.get<ReconciliationReport>(`/api/v1/reports/${jobId}/reconciliation`);
    return res.data;
  },

  async downloadReportCsv(jobId: string): Promise<Blob> {
    const res = await api.get(`/api/v1/reports/${jobId}/export`, {
      responseType: 'blob',
    });
    return res.data;
  },

  getExportUrl(jobId: string): string {
    const base = import.meta.env.VITE_API_BASE_URL || '';
    return `${base}/api/v1/reports/${jobId}/export`;
  },

  // Target Safety Check
  async testMockTarget(): Promise<TargetConnectionResponse> {
    const res = await api.get<TargetConnectionResponse>('/api/v1/targets/mock/test-connection');
    return res.data;
  },

  // Audit Events (Admin)
  async getAuditEvents(entityId?: string, page = 1, pageSize = 50): Promise<PagedAuditEvents> {
    const params: Record<string, any> = { page, page_size: pageSize };
    if (entityId) params.entity_id = entityId;
    const res = await api.get<PagedAuditEvents>('/api/v1/audit-events', { params });
    return res.data;
  },
};
