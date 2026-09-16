import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { InferenceControls } from '../src/features/inference/InferenceControls';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, runSegmentation: vi.fn() } };
});

const ready = { id: 'c1', name: 'Demo', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true };

describe('InferenceControls', () => {
  beforeEach(() => vi.clearAllMocks());
  test('is disabled for incomplete case', () => {
    render(<InferenceControls selectedCase={{ ...ready, modalities: ['DWI'], ready_for_inference: false }} onSegmentationReady={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Run AI Segmentation' })).toBeDisabled();
  });
  test('runs segmentation and reports result', async () => {
    const run = { id: 'r1', case_id: 'c1', provider: 'demo', status: 'completed', metadata: {}, created_at: '' };
    vi.mocked(api.runSegmentation).mockResolvedValue(run);
    const callback = vi.fn();
    render(<InferenceControls selectedCase={ready} onSegmentationReady={callback} />);
    await userEvent.click(screen.getByRole('button', { name: 'Run AI Segmentation' }));
    expect(callback).toHaveBeenCalledWith(run);
  });
});
