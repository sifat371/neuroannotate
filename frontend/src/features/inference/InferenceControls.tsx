import { useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { CaseSummary, InferenceRun } from '../../types/api';

type Props = { selectedCase: CaseSummary | null; onSegmentationReady: (run: InferenceRun) => void };

export function InferenceControls({ selectedCase, onSegmentationReady }: Props) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    if (!selectedCase?.ready_for_inference) return;
    setRunning(true); setError(null);
    try { onSegmentationReady(await api.runSegmentation(selectedCase.id)); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Segmentation failed.'); }
    finally { setRunning(false); }
  }
  return (
    <section className="panel inference-panel">
      <div className="panel-heading"><div><p className="eyebrow">AI pre-annotation</p><h2>Segmentation</h2></div></div>
      <p className="muted compact">Deterministic CPU demo segmentation for the portfolio workflow.</p>
      <button className="primary-button full" type="button" onClick={run} disabled={!selectedCase?.ready_for_inference || running}>
        {running ? 'Running…' : 'Run AI Segmentation'}
      </button>
      <p className="clinical-note">Demo provider — not for clinical use</p>
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
    </section>
  );
}
