import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { CaseUploadPanel } from '../src/features/cases/CaseUploadPanel';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return {
    ...actual,
    api: {
      ...actual.api,
      createCase: vi.fn(),
      createDicomCase: vi.fn(),
    },
  };
});

const createdCase = {
  id: 'case-1', name: 'Study one', created_at: '2026-09-17T12:00:00Z',
  modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>,
  ready_for_inference: true, annotation_space: 'DWI' as const, sources: [],
};

describe('CaseUploadPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  test('imports one hospital DICOM ZIP by default', async () => {
    vi.mocked(api.createDicomCase).mockResolvedValue(createdCase);
    const onCaseCreated = vi.fn();
    const user = userEvent.setup();
    render(<CaseUploadPanel selectedCase={null} onCaseChanged={() => undefined} onCaseCreated={onCaseCreated} />);

    const create = screen.getByRole('button', { name: /import case/i });
    expect(create).toBeDisabled();

    await user.type(screen.getByLabelText(/case name/i), '  Study one  ');
    await user.upload(
      screen.getByLabelText(/dicom study zip/i),
      new File(['dicom'], 'study.zip', { type: 'application/zip' }),
    );
    expect(create).toBeEnabled();

    await user.click(create);

    await waitFor(() => expect(api.createDicomCase).toHaveBeenCalledTimes(1));
    expect(api.createDicomCase).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Study one',
      study: expect.objectContaining({ name: 'study.zip' }),
    }));
    expect(onCaseCreated).toHaveBeenCalledWith(createdCase);
  });

  test('retains the atomic NIfTI triad import as an alternate path', async () => {
    vi.mocked(api.createCase).mockResolvedValue(createdCase);
    const user = userEvent.setup();
    render(<CaseUploadPanel selectedCase={null} onCaseChanged={() => undefined} onCaseCreated={() => undefined} />);

    await user.click(screen.getByRole('button', { name: /nifti triad/i }));
    await user.type(screen.getByLabelText(/case name/i), 'Study one');
    await user.upload(screen.getByLabelText(/dwi nifti/i), new File(['dwi'], 'dwi.nii.gz'));
    await user.upload(screen.getByLabelText(/adc nifti/i), new File(['adc'], 'adc.nii'));
    await user.upload(screen.getByLabelText(/flair nifti/i), new File(['flair'], 'flair.nii.gz'));

    await user.click(screen.getByRole('button', { name: /import case/i }));

    await waitFor(() => expect(api.createCase).toHaveBeenCalledTimes(1));
    expect(api.createCase).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Study one',
      dwi: expect.objectContaining({ name: 'dwi.nii.gz' }),
      adc: expect.objectContaining({ name: 'adc.nii' }),
      flair: expect.objectContaining({ name: 'flair.nii.gz' }),
    }));
  });
});
