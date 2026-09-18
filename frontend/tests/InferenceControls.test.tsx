import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { InferenceControls } from '../src/features/inference/InferenceControls';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, createInferenceJob: vi.fn(), getInferenceJob: vi.fn(), retryInferenceJob: vi.fn() } };
});

const ready = { id: 'c1', name: 'Demo', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true };
const job = (status: 'queued' | 'running' | 'completed' | 'failed') => ({
  id: 'job-1', case_id: 'c1', provider: 'demo', model_name: 'Demo', model_version: '1', service_version: '1', status,
  created_at: '2026-09-17T12:00:00Z', started_at: null, completed_at: null, segmentation_id: status === 'completed' ? 'seg-1' : null,
  failure_category: status === 'failed' ? 'provider_runtime_failure' : null,
  error_message: status === 'failed' ? 'Provider failed' : null, provenance: {},
});

describe('InferenceControls', () => {
  beforeEach(() => vi.clearAllMocks());
  test('is disabled for incomplete case', () => {
    render(<InferenceControls selectedCase={{ ...ready, modalities: ['DWI'], ready_for_inference: false }} job={null} onJobChange={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Run AI Segmentation' })).toBeDisabled();
  });
  test.each([
    ['queued', 'Queued'], ['running', 'Running'], ['completed', 'Completed'], ['failed', 'Failed'],
  ] as const)('shows the %s inference state', (status, label) => {
    render(<InferenceControls selectedCase={ready} job={job(status)} onJobChange={() => undefined} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
  test('shows retry only for a failed job and identifies the demo as a non-medical deterministic provider', async () => {
    const user = userEvent.setup();
    const callback = vi.fn();
    vi.mocked(api.retryInferenceJob).mockResolvedValue(job('queued'));
    const { rerender } = render(<InferenceControls selectedCase={ready} job={job('failed')} onJobChange={callback} />);
    expect(screen.getByText(/deterministic provider is not a trained medical model/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(callback).toHaveBeenCalledWith(job('queued'));
    rerender(<InferenceControls selectedCase={ready} job={job('completed')} onJobChange={callback} />);
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });
  test('polls active jobs every two seconds and stops after a terminal state or unmount', async () => {
    vi.useFakeTimers();
    vi.mocked(api.getInferenceJob).mockResolvedValue(job('running'));
    const { rerender, unmount } = render(<InferenceControls selectedCase={ready} job={job('queued')} onJobChange={() => undefined} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(api.getInferenceJob).toHaveBeenCalledWith('job-1');
    rerender(<InferenceControls selectedCase={ready} job={job('completed')} onJobChange={() => undefined} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(api.getInferenceJob).toHaveBeenCalledTimes(1);
    unmount();
    vi.useRealTimers();
  });
  test('creates a FastAPI inference job for a ready case', async () => {
    vi.mocked(api.createInferenceJob).mockResolvedValue(job('queued'));
    const callback = vi.fn();
    render(<InferenceControls selectedCase={ready} job={null} onJobChange={callback} />);
    await userEvent.click(screen.getByRole('button', { name: 'Run AI Segmentation' }));
    expect(api.createInferenceJob).toHaveBeenCalledWith('c1', 'demo');
    expect(callback).toHaveBeenCalledWith(job('queued'));
  });
});
