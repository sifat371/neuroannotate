import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { CaseUploadPanel } from '../src/features/cases/CaseUploadPanel';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, createCase: vi.fn() } };
});

const createdCase = {
  id: 'case-1', name: 'Study one', created_at: '2026-09-17T12:00:00Z',
  modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>,
  ready_for_inference: true, annotation_space: 'DWI' as const, sources: [],
};

describe('CaseUploadPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  test('creates one atomic triad only after a trimmed name and all three NIfTI files are supplied', async () => {
    vi.mocked(api.createCase).mockResolvedValue(createdCase);
    const onCaseCreated = vi.fn();
    const user = userEvent.setup();
    render(<CaseUploadPanel selectedCase={null} onCaseChanged={() => undefined} onCaseCreated={onCaseCreated} />);

    const create = screen.getByRole('button', { name: /create case/i });
    expect(create).toBeDisabled();
    await user.type(screen.getByLabelText(/case name/i), '  Study one  ');
    await user.upload(screen.getByLabelText(/dwi nifti/i), new File(['dwi'], 'dwi.nii.gz'));
    await user.upload(screen.getByLabelText(/adc nifti/i), new File(['adc'], 'adc.nii'));
    await user.upload(screen.getByLabelText(/flair nifti/i), new File(['flair'], 'flair.nii.gz'));
    expect(create).toBeEnabled();

    await user.click(create);

    await waitFor(() => expect(api.createCase).toHaveBeenCalledTimes(1));
    expect(api.createCase).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Study one',
      dwi: expect.objectContaining({ name: 'dwi.nii.gz' }),
      adc: expect.objectContaining({ name: 'adc.nii' }),
      flair: expect.objectContaining({ name: 'flair.nii.gz' }),
    }));
    expect(onCaseCreated).toHaveBeenCalledWith(createdCase);
  });
});
