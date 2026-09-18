import { useEffect, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { CaseSummary, InferenceJob, SystemHealth } from '../../types/api';

type Props = {
  selectedCase: CaseSummary | null;
  job: InferenceJob | null;
  onJobChange: (job: InferenceJob) => void;
  health?: SystemHealth | null;
};

const activeStatuses = new Set(['queued', 'running']);

export function InferenceControls({ selectedCase, job, onJobChange, health }: Props) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!job || !activeStatuses.has(job.status)) return;
    let live = true;
    const interval = window.setInterval(() => {
      void api.getInferenceJob(job.id).then((next) => {
        if (live) onJobChange(next);
      }).catch((err) => {
        if (live) setError(err instanceof ApiError ? err.message : 'Could not refresh inference status.');
      });
    }, 2000);
    return () => { live = false; window.clearInterval(interval); };
  }, [job?.id, job?.status, onJobChange]);

  async function run() {
    if (!selectedCase?.ready_for_inference) return;
    setRunning(true); setError(null);
    const provider = health?.inference?.mode === 'gpu' ? 'deepisles' : 'demo';
    try { onJobChange(await api.createInferenceJob(selectedCase.id, provider)); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Segmentation failed.'); }
    finally { setRunning(false); }
  }
  async function retry() {
    if (!job || job.status !== 'failed') return;
    setError(null);
    try { onJobChange(await api.retryInferenceJob(job.id)); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Could not retry inference.'); }
  }
  const status = job ? `${job.status[0].toUpperCase()}${job.status.slice(1)}` : 'Not started';
  const isActive = job ? activeStatuses.has(job.status) : false;
  const gpuMode = health?.inference?.mode === 'gpu';
  const gpuReady = health?.inference?.deepisles === 'ready' && health.inference.ready;
  const inferenceUnavailable = gpuMode && !gpuReady;
  return (
    <section className="panel inference-panel">
      <div className="panel-heading"><div><p className="eyebrow">AI pre-annotation</p><h2>Segmentation</h2></div></div>
      {gpuMode ? (
        <p className="muted compact">DeepISLES {health?.inference?.model_version ?? ''} on {health?.inference?.device ?? 'an unavailable device'}.</p>
      ) : <p className="muted compact">The deterministic provider is not a trained medical model.</p>}
      <p className={`inference-state ${job?.status ?? 'idle'}`}>Status: <strong>{status}</strong></p>
      {job?.status === 'failed' && job.error_message ? <p className="error-banner">{job.error_message}</p> : null}
      <button className="primary-button full" type="button" onClick={() => void run()} disabled={!selectedCase?.ready_for_inference || running || isActive || inferenceUnavailable}>
        {running || isActive ? 'Running…' : 'Run AI Segmentation'}
      </button>
      {job?.status === 'failed' ? <button className="secondary-button full retry-button" type="button" onClick={() => void retry()}>Retry inference</button> : null}
      {inferenceUnavailable ? <p className="error-banner">GPU provider is unavailable. Start the GPU profile and wait for DeepISLES readiness.</p> : null}
      <p className="clinical-note">{gpuMode ? 'DeepISLES provider — research software only' : 'Demo provider — research software only'}</p>
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
    </section>
  );
}
