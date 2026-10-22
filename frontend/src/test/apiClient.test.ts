import { describe, expect, it, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { apiClient, ApiError } from '../api/client';

describe('apiClient', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
  });

  it('instantiates ApiError with code and status', () => {
    const error = new ApiError('Failed', 'SOURCE_NOT_FOUND', 404, { detail: 'not found' });
    expect(error.name).toBe('ApiError');
    expect(error.message).toBe('Failed');
    expect(error.code).toBe('SOURCE_NOT_FOUND');
    expect(error.status).toBe(404);
  });

  it('generates export report URL with base URL', () => {
    const url = apiClient.getExportUrl('job-123');
    expect(url).toContain('/api/v1/reports/job-123/export');
  });
});
