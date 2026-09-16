import type { CaseSummary, InferenceRun, Modality, Revision } from '../types/api';
import type { SerializedLabelmap } from '../cornerstone/serializeLabelmap';

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

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

export const api = {
  listCases: () => request<CaseSummary[]>('/api/cases'),
  createCase: (name: string) => request<CaseSummary>('/api/cases', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }),
  uploadModality: (caseId: string, modality: Modality, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<CaseSummary>(`/api/cases/${caseId}/modalities/${modality}`, { method: 'POST', body: form });
  },
  getModalityFileUrl: (caseId: string, modality: Modality) => `${API_BASE}/api/cases/${caseId}/modalities/${modality}/file`,
  runSegmentation: (caseId: string) => request<InferenceRun>(`/api/cases/${caseId}/segment`, { method: 'POST' }),
  getLatestSegmentation: async (caseId: string): Promise<InferenceRun | null> => {
    try {
      return await request<InferenceRun>(`/api/cases/${caseId}/segmentations/latest`);
    } catch (error) {
      if (error instanceof ApiError && error.code === 'segmentation_not_found') return null;
      throw error;
    }
  },
  getLatestSegmentationFileUrl: (caseId: string) => `${API_BASE}/api/cases/${caseId}/segmentations/latest/file`,
  listRevisions: (caseId: string) => request<Revision[]>(`/api/cases/${caseId}/revisions`),
  saveRevision: (caseId: string, sourceInferenceId: string, data: SerializedLabelmap, note?: string) => {
    const form = new FormData();
    const copy = new Uint8Array(data.voxels);
    form.append('voxels', new Blob([copy], { type: 'application/octet-stream' }), 'labelmap.bin');
    form.append('shape', JSON.stringify(data.shape));
    form.append('source_inference_id', sourceInferenceId);
    if (note?.trim()) form.append('note', note.trim());
    return request<Revision>(`/api/cases/${caseId}/revisions`, { method: 'POST', body: form });
  },
  getRevisionFileUrl: (caseId: string, revisionId: string) => `${API_BASE}/api/cases/${caseId}/revisions/${revisionId}/file`,
  getExportUrl: (caseId: string, revisionId: string) => `${API_BASE}/api/cases/${caseId}/export?revision_id=${encodeURIComponent(revisionId)}`,
};
