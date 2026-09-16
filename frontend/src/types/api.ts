export type Modality = 'DWI' | 'ADC' | 'FLAIR';

export type CaseSummary = {
  id: string;
  name: string;
  created_at: string;
  modalities: Modality[];
  ready_for_inference: boolean;
};

export type InferenceRun = {
  id: string;
  case_id: string;
  provider: string;
  status: string;
  metadata: Record<string, string | number | boolean>;
  created_at: string;
};

export type Revision = {
  id: string;
  case_id: string;
  source_inference_id: string;
  note: string | null;
  created_at: string;
};
