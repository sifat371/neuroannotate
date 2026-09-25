import type {
  CaseDetail,
  CaseSummary,
  ExportArtifact,
  InferenceJob,
  Modality,
  ProviderInfo,
  Revision,
  SystemHealth,
} from '../types/api';
import type { SerializedLabelmap } from '../cornerstone/serializeLabelmap';

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

export type CreateCaseInput = {
  name: string;
  dwi: File;
  adc: File;
  flair: File;
};

export type CreateDicomCaseInput = {
  name: string;
  study: File;
};

export type SaveRevisionInput = {
  data: SerializedLabelmap;
  note?: string;
} & (
  | { sourceInferenceId: string; sourceSegmentationId?: never; parentRevisionId?: never }
  | { sourceInferenceId?: never; sourceSegmentationId: string; parentRevisionId?: never }
  | { sourceInferenceId?: never; sourceSegmentationId?: never; parentRevisionId: string }
);

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let code = 'request_failed';
    let message = `Request failed with status ${response.status}`;
    try {
      const body = await response.json() as { error?: { code?: string; message?: string } };
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      // Non-JSON errors retain the safe fallback message above.
    }
    throw new ApiError(code, message, response.status);
  }
  return response.json() as Promise<T>;
}

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export function sourceFileUrl(caseId: string, modality: Modality): string {
  return apiUrl(`/api/cases/${caseId}/modalities/${modality}/file.nii.gz`);
}

export function segmentationFileUrl(segmentationId: string): string {
  return apiUrl(`/api/segmentations/${segmentationId}/file.nii.gz`);
}

export function revisionFileUrl(revisionId: string): string {
  return apiUrl(`/api/revisions/${revisionId}/file.nii.gz`);
}

export function exportMaskUrl(exportId: string): string {
  return apiUrl(`/api/exports/${exportId}/mask`);
}

export function exportProvenanceUrl(exportId: string): string {
  return apiUrl(`/api/exports/${exportId}/provenance`);
}

export function exportBundleUrl(exportId: string): string {
  return apiUrl(`/api/exports/${exportId}/bundle`);
}

export async function createCase(input: CreateCaseInput): Promise<CaseDetail> {
  const body = new FormData();
  body.set('name', input.name);
  body.set('dwi', input.dwi);
  body.set('adc', input.adc);
  body.set('flair', input.flair);
  return request<CaseDetail>('/api/cases', { method: 'POST', body });
}

export async function createDicomCase(input: CreateDicomCaseInput): Promise<CaseDetail> {
  const body = new FormData();
  body.set('name', input.name);
  body.set('study', input.study);
  return request<CaseDetail>('/api/cases/dicom', { method: 'POST', body });
}

export function createInferenceJob(caseId: string, provider = 'demo'): Promise<InferenceJob> {
  return request<InferenceJob>(`/api/cases/${caseId}/inference-jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider }),
  });
}

export function listInferenceJobs(caseId: string): Promise<InferenceJob[]> {
  return request<InferenceJob[]>(`/api/cases/${caseId}/inference-jobs`);
}

export function getInferenceJob(jobId: string): Promise<InferenceJob> {
  return request<InferenceJob>(`/api/inference-jobs/${jobId}`);
}

export function retryInferenceJob(jobId: string): Promise<InferenceJob> {
  return request<InferenceJob>(`/api/inference-jobs/${jobId}/retry`, { method: 'POST' });
}

export function listProviders(): Promise<ProviderInfo[]> {
  return request<ProviderInfo[]>('/api/inference/providers');
}

export function getSystemHealth(): Promise<SystemHealth> {
  return request<SystemHealth>('/health');
}

export function listRevisions(caseId: string): Promise<Revision[]> {
  return request<Revision[]>(`/api/cases/${caseId}/revisions`);
}

export function saveRevision(caseId: string, input: SaveRevisionInput): Promise<Revision>;
export function saveRevision(
  caseId: string,
  sourceInferenceId: string,
  data: SerializedLabelmap,
  note?: string,
): Promise<Revision>;
export function saveRevision(
  caseId: string,
  inputOrSourceInferenceId: SaveRevisionInput | string,
  legacyData?: SerializedLabelmap,
  legacyNote?: string,
): Promise<Revision> {
  let input: SaveRevisionInput;
  if (typeof inputOrSourceInferenceId === 'string') {
    if (!legacyData) throw new Error('Revision labelmap data is required');
    input = { data: legacyData, sourceInferenceId: inputOrSourceInferenceId, note: legacyNote };
  } else {
    input = inputOrSourceInferenceId;
  }
  const body = new FormData();
  const copy = new Uint8Array(input.data.voxels);
  body.append('voxels', new Blob([copy], { type: 'application/octet-stream' }), 'labelmap.bin');
  body.append('shape', JSON.stringify(input.data.shape));
  if (input.sourceInferenceId) body.append('source_inference_id', input.sourceInferenceId);
  if (input.sourceSegmentationId) body.append('source_segmentation_id', input.sourceSegmentationId);
  if (input.parentRevisionId) body.append('parent_revision_id', input.parentRevisionId);
  if (input.note?.trim()) body.append('note', input.note.trim());
  return request<Revision>(`/api/cases/${caseId}/revisions`, { method: 'POST', body });
}

export function createExport(caseId: string, revisionId: string): Promise<ExportArtifact> {
  return request<ExportArtifact>(`/api/cases/${caseId}/exports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ revision_id: revisionId }),
  });
}

export const api = {
  listCases: () => request<CaseSummary[]>('/api/cases'),
  getCase: (caseId: string) => request<CaseDetail>(`/api/cases/${caseId}`),
  createCase,
  createDicomCase,
  createInferenceJob,
  listInferenceJobs,
  getInferenceJob,
  retryInferenceJob,
  listProviders,
  getSystemHealth,
  listRevisions,
  saveRevision,
  createExport,
  sourceFileUrl,
  segmentationFileUrl,
  revisionFileUrl,
  exportMaskUrl,
  exportProvenanceUrl,
  exportBundleUrl,

};
