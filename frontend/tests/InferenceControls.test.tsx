import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { InferenceControls } from '../src/features/inference/InferenceControls';
import type { SystemHealth } from '../src/types/api';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, createInferenceJob: vi.fn(), getInferenceJob: vi.fn(), retryInferenceJob: vi.fn() } };
});

const ready = { id: 'c1', name: 'Demo', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true };
const demoHealth: SystemHealth = {
  status: 'ok', service: 'neuroannotate-api', storage: 'ok', database: 'ok',
  inference: { mode: 'demo', deepisles: 'not_enabled', ready: true },
};
const job = (status: 'queued' | 'running' | 'completed' | 'failed') => ({
  id: 'job-1', case_id: 'c1', provider: 'demo', model_name: 'Demo', model_version: '1', service_version: '1', status,
  created_at: '2026-09-17T12:00:00Z', started_at: null, completed_at: null, segmentation_id: status === 'completed' ? 'seg-1' : null,
  failure_category: status === 'failed' ? 'provider_runtime_failure' : null,
  error_message: status === 'failed' ? 'Provider failed' : null, provenance: {},
});

describe('InferenceControls', () => {
  beforeEach(() => vi.clearAllMocks());

  test('is disabled for incomplete case', () => {
    render(<InferenceControls selectedCase={{ ...ready, modalities: ['DWI'], ready_for_inference: false }} job={null} onJobChange={() => undefined} health={demoHealth} />);
    expect(screen.getByRole('button', { name: 'Run AI Segmentation' })).toBeDisabled();
  });

  test.each([
    ['queued', 'Queued'], ['running', 'Running'], ['completed', 'Completed'], ['failed', 'Failed'],
  ] as const)('shows the %s inference state', (status, label) => {
    render(<InferenceControls selectedCase={ready} job={job(status)} onJobChange={() => undefined} health={demoHealth} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  test('waits for an explicit health mode instead of silently assuming demo', () => {
    const { rerender } = render(<InferenceControls selectedCase={ready} job={null} onJobChange={() => undefined} health={null} />);
    expect(screen.getByRole('button', { name: 'Run AI Segmentation' })).toBeDisabled();
    expect(screen.getByText(/readiness is unknown/i)).toBeInTheDocument();
    rerender(<InferenceControls selectedCase={ready} job={null} onJobChange={() => undefined} health={demoHealth} />);
    expect(screen.getByRole('button', { name: 'Run AI Segmentation' })).toBeEnabled();
  });

  test('shows retry only for a failed job and identifies the demo as a non-medical deterministic provider', async () => {
    const user = userEvent.setup();
    const callback = vi.fn();
    vi.mocked(api.retryInferenceJob).mockResolvedValue(job('queued'));
    const { rerender } = render(<InferenceControls selectedCase={ready} job={job('failed')} onJobChange={callback} health={demoHealth} />);
    expect(screen.getByText(/deterministic provider is not a trained medical model/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(callback).toHaveBeenCalledWith(job('queued'));
    rerender(<InferenceControls selectedCase={ready} job={job('completed')} onJobChange={callback} health={demoHealth} />);
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });

  test('polls active jobs every two seconds and stops after a terminal state or unmount', async () => {
    vi.useFakeTimers();
    vi.mocked(api.getInferenceJob).mockResolvedValue(job('running'));
    const { rerender, unmount } = render(<InferenceControls selectedCase={ready} job={job('queued')} onJobChange={() => undefined} health={demoHealth} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(api.getInferenceJob).toHaveBeenCalledWith('job-1');
    rerender(<InferenceControls selectedCase={ready} job={job('completed')} onJobChange={() => undefined} health={demoHealth} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(api.getInferenceJob).toHaveBeenCalledTimes(1);
    unmount();
    vi.useRealTimers();
  });

  test('creates a FastAPI inference job for a ready case only after demo readiness is known', async () => {
    vi.mocked(api.createInferenceJob).mockResolvedValue(job('queued'));
    const callback = vi.fn();
    render(<InferenceControls selectedCase={ready} job={null} onJobChange={callback} health={demoHealth} />);
    await userEvent.click(screen.getByRole('button', { name: 'Run AI Segmentation' }));
    expect(api.createInferenceJob).toHaveBeenCalledWith('c1', 'demo');
    expect(callback).toHaveBeenCalledWith(job('queued'));
  });

  test('requires an explicit load action for a newly completed segmentation', async () => {
    const onLoadCompleted = vi.fn();
    render(<InferenceControls selectedCase={ready} job={job('completed')} onJobChange={() => undefined} health={demoHealth} loadedSegmentationId="seg-old" onLoadCompleted={onLoadCompleted} />);
    expect(onLoadCompleted).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Load Segmentation' }));
    expect(onLoadCompleted).toHaveBeenCalledWith(job('completed'));
  });

  test('does not offer load when the completed segmentation is already active', () => {
    render(<InferenceControls selectedCase={ready} job={job('completed')} onJobChange={() => undefined} health={demoHealth} loadedSegmentationId="seg-1" onLoadCompleted={() => undefined} />);
    expect(screen.queryByRole('button', { name: 'Load Segmentation' })).not.toBeInTheDocument();
    expect(screen.getByText(/segmentation is loaded/i)).toBeInTheDocument();
  });

  test('submits the ready GPU provider through FastAPI and identifies its service', async () => {
    vi.mocked(api.createInferenceJob).mockResolvedValue(job('queued'));
    render(<InferenceControls
      selectedCase={ready}
      job={null}
      onJobChange={() => undefined}
      health={{
        status: 'ok', service: 'neuroannotate-api', storage: 'ok', database: 'ok',
        inference: {
          mode: 'gpu', deepisles: 'ready', ready: true,
          model_name: 'DeepISLES', model_version: '7658b608fc0d890cf14448ff3e58c47ad5c761e7',
          device: 'cuda:0', cuda_available: true,
        },
      }}
    />);
    expect(screen.getByText(/DeepISLES.*cuda:0/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Run AI Segmentation' }));
    expect(api.createInferenceJob).toHaveBeenCalledWith('c1', 'deepisles');
  });

  test('disables inference when the explicitly selected GPU provider is unavailable', () => {
    render(<InferenceControls
      selectedCase={ready}
      job={null}
      onJobChange={() => undefined}
      health={{ status: 'ok', service: 'neuroannotate-api', storage: 'ok', database: 'ok', inference: { mode: 'gpu', deepisles: 'unavailable', ready: false } }}
    />);
    expect(screen.getByRole('button', { name: 'Run AI Segmentation' })).toBeDisabled();
    expect(screen.getByText(/GPU provider is unavailable/i)).toBeInTheDocument();
  });

  test('blocks a failed GPU retry while its provider is unavailable', async () => {
    render(<InferenceControls
      selectedCase={ready}
      job={{ ...job('failed'), provider: 'deepisles' }}
      onJobChange={() => undefined}
      health={{ status: 'ok', service: 'neuroannotate-api', storage: 'ok', database: 'ok', inference: { mode: 'gpu', deepisles: 'unavailable', ready: false } }}
    />);
    const retry = screen.getByRole('button', { name: /retry inference/i });
    expect(retry).toBeDisabled();
    await userEvent.click(retry);
    expect(api.retryInferenceJob).not.toHaveBeenCalled();
  });

  test.each([
    { mode: 'legacy' as const, provider: 'nnunet' as const, description: /legacy nnU-Net provider is unavailable/i, disclaimer: /legacy nnU-Net provider — research software only/i },
    { mode: 'unknown' as const, provider: 'unknown' as const, description: /configured inference provider is unrecognized/i, disclaimer: /unavailable provider — research software only/i },
  ])('does not submit an unavailable $mode configured provider', ({ mode, provider, description, disclaimer }) => {
    render(<InferenceControls
      selectedCase={ready}
      job={null}
      onJobChange={() => undefined}
      health={{ status: 'ok', service: 'neuroannotate-api', storage: 'ok', database: 'ok', inference: { mode, deepisles: 'not_enabled', ready: false, provider } }}
    />);
    expect(screen.getByRole('button', { name: 'Run AI Segmentation' })).toBeDisabled();
    expect(screen.getByText(/configured inference provider is unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(description)).toBeInTheDocument();
    expect(screen.getByText(disclaimer)).toBeInTheDocument();
    expect(screen.queryByText(/Demo provider — research software only/i)).not.toBeInTheDocument();
  });
});
