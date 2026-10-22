export type IssueSeverity = 'WARNING' | 'REJECTED';

export interface ValidationIssue {
  code: string;
  severity: IssueSeverity;
  message: string;
  sheet?: string | null;
  row?: number | null;
  field?: string | null;
  raw_value?: string | null;
}

export interface SheetSchema {
  name: string;
  max_row: number;
  max_column: number;
  headers: string[];
  inferred_types: Record<string, string>;
  issues: ValidationIssue[];
}

export interface SourceResponse {
  source_id: string;
  original_filename: string;
  sha256: string;
  created_at: string;
  sheets: SheetSchema[];
}

export interface PagedSources {
  items: SourceResponse[];
  page: number;
  page_size: number;
  total: number;
}

export type MappingType = 'direct' | 'transformed' | 'derived' | 'excluded' | 'unresolved';
export type MappingStatus = 'proposed' | 'approved' | 'rejected' | 'unresolved';

export interface TransformationConfig {
  trim?: boolean;
  uppercase?: boolean;
  lowercase?: boolean;
  date_format?: {
    source_format: string;
    target_format: string;
  };
  value_map?: Record<string, string>;
  default_value?: any;
  [key: string]: any;
}

export interface MappingCreate {
  source_id: string;
  source_entity: string;
  source_sheet: string;
  source_field: string;
  target_entity: string;
  target_field: string;
  mapping_type: MappingType;
  status?: MappingStatus;
  required?: boolean;
  transformation?: TransformationConfig | null;
  notes?: string | null;
}

export interface MappingUpdate {
  source_entity?: string;
  source_sheet?: string;
  source_field?: string;
  target_entity?: string;
  target_field?: string;
  mapping_type?: MappingType;
  required?: boolean;
  transformation?: TransformationConfig | null;
  notes?: string | null;
}

export interface MappingResponse extends MappingCreate {
  mapping_id: string;
  version: number;
  created_at: string;
  created_by?: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
}

export type JobStatus =
  | 'PENDING'
  | 'VALIDATING'
  | 'READY'
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'COMPLETED_WITH_ERRORS'
  | 'FAILED'
  | 'CANCELLED';

export interface ProfileSheetResult {
  sheet: string;
  populated_rows: number;
  empty_structural_rows: number;
  null_counts: Record<string, number>;
  duplicate_rows: number;
}

export interface ProfileResult {
  sheets?: ProfileSheetResult[];
  row_count?: number;
  column_count?: number;
  null_counts?: Record<string, number>;
  type_profile?: Record<string, string>;
  sample_values?: Record<string, any[]>;
  issues?: string[] | ValidationIssue[];
  [key: string]: any;
}

export interface PreviewRecord {
  sheet: string;
  row: number;
  target_entity: string;
  proposed: Record<string, any>;
}

export interface PreviewRow {
  row_number?: number;
  source?: Record<string, any>;
  target?: Record<string, any>;
  sheet?: string;
  row?: number;
  target_entity?: string;
  proposed?: Record<string, any>;
  [key: string]: any;
}

export interface PreviewResult {
  records_evaluated?: number;
  eligible_records?: number;
  structural_empty_rows?: number;
  records?: PreviewRecord[];
  warnings?: any[];
  issues?: any[];
  rejected_records?: number;
  equus_writes?: boolean | string;
  // Backward compatibility fields
  status?: string;
  evaluated_rows?: number;
  migrated_rows?: number;
  field_counts?: Record<string, number>;
  preview_rows?: PreviewRow[];
  mapping_id?: string;
  mapping_versions?: Record<string, number>;
  [key: string]: any;
}

export interface JobResponse {
  job_id: string;
  kind: 'profile' | 'preview' | string;
  source_id: string;
  status: JobStatus;
  progress: number;
  attempts: number;
  created_at: string;
  updated_at: string;
  result?: ProfileResult | PreviewResult | any;
  failure_code?: string | null;
  cancellation_requested: boolean;
  mapping_id?: string;
}

export interface AuditEvent {
  entity_id: string;
  action: string;
  actor: string;
  timestamp: string;
  job_id?: string | null;
  metadata?: Record<string, any>;
}

export interface PagedAuditEvents {
  items: AuditEvent[];
  page: number;
  page_size: number;
  total: number;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  database: 'connected' | 'not_configured_or_unavailable';
  equus_writes: 'disabled' | 'enabled';
}

export interface ReconciliationReport {
  source_records?: number;
  accepted_records?: number;
  rejected_records?: number;
  warning_count?: number;
  issue_count?: number;
  target_reconciliation?: string;
  target_record_count?: number;
  reconciled?: boolean;
  summary?: Record<string, any>;
  details?: Record<string, any>;
  [key: string]: any;
}

export interface TargetConnectionResponse {
  target: string;
  connected: boolean;
  writes_allowed: boolean;
  safety_note: string;
}

export interface UserSession {
  subject: string;
  token: string;
  roles: string[];
}
