export type Modality = 'DWI' | 'ADC' | 'FLAIR';

export type InferenceStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface CaseSummary {
  id: string;
  name: string;
  created_at: string;
  modalities: Modality[];
  ready_for_inference: boolean;
}

export interface SourceArtifact {
  id: string;
  modality: Modality;
  original_filename: string;
  relative_path: string;
  sha256: string;
  file_size: number;
  shape: [number, number, number];
  spacing: [number, number, number];
  affine: number[][];
  datatype: string;
  created_at: string;
}

export interface CaseDetail extends CaseSummary {
  annotation_space: 'DWI';
  sources: SourceArtifact[];
}

export interface InferenceJob {
  id: string;
  case_id: string;
  provider: string;
  model_name: string;
  model_version: string;
  service_version: string;
  status: InferenceStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  segmentation_id: string | null;
  failure_category: string | null;
  error_message: string | null;
  provenance: Record<string, unknown>;
}

export interface ProviderInfo {
  name: string;
  model_name: string;
  model_version: string;
  service_version: string;
  available: boolean;
}

export interface Revision {
  id: string;
  case_id: string;
  source_inference_id: string;
  source_segmentation_id: string;
  parent_revision_id: string | null;
  sha256: string | null;
  edit_stats: Record<string, number>;
  note: string | null;
  created_at: string;
}

export interface ExportArtifact {
  id: string;
  case_id: string;
  revision_id: string;
  mask_sha256: string;
  created_at: string;
  mask_url: string;
  provenance_url: string;
  bundle_url: string;
}

export interface SystemHealth {
  status: 'ok';
  service: 'neuroannotate-api';
}

// Compatibility contract for the temporary pre-v1 segmentation route.
export interface InferenceRun {
  id: string;
  case_id: string;
  provider: string;
  status: string;
  metadata: Record<string, string | number | boolean>;
  created_at: string;
}
