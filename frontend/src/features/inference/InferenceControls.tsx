import { useEffect, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { CaseSummary, InferenceJob, SystemHealth } from '../../types/api';

type Props = {
  selectedCase: CaseSummary | null;
  job: InferenceJob | null;
  onJobChange: (job: InferenceJob) => void;
  health?: SystemHealth | null;
  loadedSegmentationId?: string | null;
  onLoadCompleted?: (job: InferenceJob) => void;
};

const activeStatuses = new Set(['queued', 'running']);

export function InferenceControls({
  selectedCase,
  job,
  onJobChange,
  health,
  loadedSegmentationId = null,
  onLoadCompleted,
}: Props) {
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

  const inferenceHealth = health?.inference;
  const gpuMode = inferenceHealth?.mode === 'gpu';
  const demoReady = inferenceHealth?.mode === 'demo' && inferenceHealth.ready;
  const gpuReady = gpuMode && inferenceHealth.deepisles === 'ready' && inferenceHealth.ready;
  const inferenceUnavailable = !inferenceHealth || !(demoReady || gpuReady);

  async function run() {
    if (!selectedCase?.ready_for_inference || inferenceUnavailable || !inferenceHealth) return;
    const provider = inferenceHealth.mode === 'gpu' ? 'deepisles' : inferenceHealth.mode === 'demo' ? 'demo' : null;
    if (!provider) return;
    setRunning(true);
    setError(null);
    try { onJobChange(await api.createInferenceJob(selectedCase.id, provider)); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Segmentation failed.'); }
    finally { setRunning(false); }
  }

  async function retry() {
    if (!job || job.status !== 'failed' || inferenceUnavailable) return;
    setError(null);
    try { onJobChange(await api.retryInferenceJob(job.id)); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Could not retry inference.'); }
  }

  const status = job ? `${job.status[0].toUpperCase()}${job.status.slice(1)}` : 'Not started';
  const isActive = job ? activeStatuses.has(job.status) : false;
  const canLoadCompleted = Boolean(
    job?.status === 'completed'
    && job.segmentation_id
    && job.segmentation_id !== loadedSegmentationId
    && onLoadCompleted,
  );
  const providerDescription = !inferenceHealth
    ? 'Checking inference provider readiness…'
    : gpuMode
      ? `DeepISLES ${inferenceHealth.model_version ?? ''} on ${inferenceHealth.device ?? 'an unavailable device'}.`
      : inferenceHealth.mode === 'legacy'
        ? 'Legacy nnU-Net provider is unavailable.'
        : inferenceHealth.mode === 'unknown'
          ? 'The configured inference provider is unrecognized.'
          : 'The deterministic provider is not a trained medical model.';
  const providerDisclaimer = !inferenceHealth
    ? 'Provider readiness pending — research software only'
    : gpuMode
      ? 'DeepISLES provider — research software only'
      : inferenceHealth.mode === 'legacy'
        ? 'Legacy nnU-Net provider — research software only'
        : inferenceHealth.mode === 'unknown'
          ? 'Unavailable provider — research software only'
          : 'Demo provider — research software only';

  return (
    <section className="panel inference-panel">
      <div className="panel-heading"><div><p className="eyebrow">AI pre-annotation</p><h2>Segmentation</h2></div></div>
      <p className="muted compact">{providerDescription}</p>
      <p className={`inference-state ${job?.status ?? 'idle'}`}>Status: <strong>{status}</strong></p>
      {job?.status === 'failed' && job.error_message ? <p className="error-banner">{job.error_message}</p> : null}
      <button className="primary-button full" type="button" onClick={() => void run()} disabled={!selectedCase?.ready_for_inference || running || isActive || inferenceUnavailable}>
        {running || isActive ? 'Running…' : 'Run AI Segmentation'}
      </button>
      {canLoadCompleted ? <button className="secondary-button full" type="button" onClick={() => job && onLoadCompleted?.(job)}>Load Segmentation</button> : null}
      {job?.status === 'completed' && job.segmentation_id === loadedSegmentationId ? <p className="muted">This segmentation is loaded.</p> : null}
      {job?.status === 'failed' ? <button className="secondary-button full retry-button" type="button" onClick={() => void retry()} disabled={inferenceUnavailable}>Retry inference</button> : null}
      {inferenceUnavailable ? <p className="error-banner">{
        !inferenceHealth
          ? 'Inference provider readiness is unknown. Waiting for the backend health check.'
          : gpuMode
            ? 'GPU provider is unavailable. Start the GPU profile and wait for DeepISLES readiness.'
            : 'Configured inference provider is unavailable.'
      }</p> : null}
      <p className="clinical-note">{providerDisclaimer}</p>
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
    </section>
  );
}
