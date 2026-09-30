import type { components } from './generated-api';
export type AnalysisRequest = components['schemas']['AnalysisRequest'];
export type Column = components['schemas']['Column'];
export type Row = { x: { raw: string; value: number }; y: { raw: string; value: number }; point_index?: number };
export type Project = { id: string; title: string; course_label: string | null; unit_label: string | null; permission: 'owner'; updated_at: string; created_at: string; latest_dataset_version: number | null };
export type Dataset = { id: string; project_id: string; display_name: string; version_number: number; row_count: number; content_sha256: string; created_at: string; columns: Column[]; rows?: Row[]; next_offset?: number | null };
export type Finding = { rule_id: string; severity: 'info' | 'warning' | 'error'; blocking: boolean; message: string; evidence: Record<string, unknown> };
export type Coefficient = { key: 'intercept' | 'linear' | 'quadratic'; ordinal: number; value: number; standard_error: number; unit: string; dimension: Record<string, number> };
export type Point = { point_index: number; transformed_x: number; transformed_y: number; predicted_y: number; residual: number };
export type AnalysisSummary = { id: string; status: 'succeeded' | 'rejected' | 'failed'; dataset_version_id: string; created_at: string; configuration: AnalysisRequest; engine_version: string; rule_set_version: string; supersedes_analysis_id: string | null };
export type Analysis = {
  analysis: AnalysisSummary; status: AnalysisSummary['status']; findings: Finding[]; coefficients?: Coefficient[];
  metrics?: { n: number; parameter_count: number; degrees_of_freedom: number; sse: number; rmse: number; mae: number; r_squared: number | null; condition_number: number };
  series?: Point[]; chart_summary?: string;
  provenance: { canonical_units: { x: string; y: string }; transformed_x_unit?: string; original_units: { x: string; y: string }; dataset_sha256: string; scientific_sha256: string; origin_shift?: { original: number | null; canonical: number; canonical_unit: string }; request: AnalysisRequest };
};
export type Explanation = { id: string; status: 'succeeded' | 'failed'; text: string | null; fallback_text: string; failure_code: string | null };
export type Session = { principal: { id: string; expires_at: string }; csrf: { token: string }; capabilities: { ai: boolean }; retention_days: number };
export type Page<T> = { items: T[]; next_cursor: string | null };
