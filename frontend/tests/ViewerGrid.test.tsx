import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';

vi.mock('../src/cornerstone/viewer', () => ({
  createViewerSession: vi.fn().mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() }),
}));
vi.mock('../src/cornerstone/segmentation', async (importOriginal) => ({
  ...await importOriginal<typeof import('../src/cornerstone/segmentation')>(),
  attachLabelmap: vi.fn(),
  setOverlayVisible: vi.fn(),
  setOverlayOpacity: vi.fn(),
}));
vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>();
  return { ...actual, api: { ...actual.api, getCase: vi.fn() } };
});

import { ViewerGrid } from '../src/features/viewer/ViewerGrid';
import { api } from '../src/api/client';
import { attachLabelmap } from '../src/cornerstone/segmentation';
import { createViewerSession } from '../src/cornerstone/viewer';
import type { CaseDetail, SourceArtifact } from '../src/types/api';

const selectedCase = { id: 'case-1', name: 'Case one', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true };
const authoritativeDwi = {
  shape: [64, 64, 24] as [number, number, number],
  affine: [[0.05, -1.8, 0.18, -20], [1.2, 0.16, 0.23, 15], [0.1, 0.12, 3.4, -30], [0, 0, 0, 1]],
};
const authoritativeFlair = { ...authoritativeDwi, affine: [[0.05, -1.55, 0.18, -20], [1.2, 0.16, 0.23, 15], [0.1, 0.12, 3.4, -30], [0, 0, 0, 1]] };

function source(modality: SourceArtifact['modality'], geometry = authoritativeDwi): SourceArtifact {
  return {
    id: `${modality.toLowerCase()}-source`, modality, original_filename: `${modality.toLowerCase()}.nii.gz`, relative_path: `source/${modality.toLowerCase()}.nii.gz`,
    sha256: 'a'.repeat(64), file_size: 1, shape: geometry.shape, spacing: [1.2, 1.8, 3.4], affine: geometry.affine, datatype: 'float32', created_at: '',
  };
}

function caseDetail(sources: SourceArtifact[] = [source('DWI'), source('ADC'), source('FLAIR', authoritativeFlair)]): CaseDetail {
  return { ...selectedCase, annotation_space: 'DWI', sources };
}

function editableLabelmap(id = 'seg-ui') {
  return {
    segmentationId: id, volumeId: `vol-${id}`, sourceInferenceId: 'job-1', visible: true, opacity: 0.5, dirty: false, editCount: 0,
    setEditingTool: vi.fn(), setBrushSize: vi.fn(), undo: vi.fn(), redo: vi.fn(),
    getCurrentLabelmap: () => ({ shape: [1, 1, 1] as [number, number, number], voxels: new Uint8Array([0]) }),
    markSaved: vi.fn(), replaceFromNifti: vi.fn().mockResolvedValue(true), destroy: vi.fn(),
  };
}

afterEach(() => {
  vi.mocked(createViewerSession).mockReset();
  vi.mocked(api.getCase).mockReset();
  vi.mocked(attachLabelmap).mockReset();
});

test('mounts all three orthogonal viewport containers', () => {
  render(<ViewerGrid selectedCase={null} modality="DWI" inference={null} overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  expect(screen.getByLabelText('Axial MRI viewport')).toBeInTheDocument();
  expect(screen.getByLabelText('Sagittal MRI viewport')).toBeInTheDocument();
  expect(screen.getByLabelText('Coronal MRI viewport')).toBeInTheDocument();
});

test('applies the latest revision selected before its editable labelmap becomes ready', async () => {
  let resolveLabelmap!: (value: import('../src/cornerstone/segmentation').EditableSegmentation) => void;
  const labelmap = editableLabelmap();
  vi.mocked(attachLabelmap).mockImplementationOnce(() => new Promise((resolve) => { resolveLabelmap = resolve; }));
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never);
  vi.mocked(api.getCase).mockResolvedValue(caseDetail());
  const { rerender } = render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} revisionUrl="/old-revision.nii.gz" overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  rerender(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} revisionUrl="/latest-revision.nii.gz" overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalled());
  await act(async () => { resolveLabelmap(labelmap); });
  await waitFor(() => expect(labelmap.replaceFromNifti).toHaveBeenCalledWith('/latest-revision.nii.gz', expect.any(Function)));
  expect(labelmap.replaceFromNifti).toHaveBeenCalledTimes(1);
});

test('uses authoritative anisotropic oblique and sheared metadata rather than normalized display geometry', async () => {
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never);
  vi.mocked(api.getCase).mockResolvedValue(caseDetail());
  vi.mocked(attachLabelmap).mockResolvedValue(editableLabelmap());
  render(<ViewerGrid selectedCase={selectedCase} modality="FLAIR" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);

  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  expect(attachLabelmap).not.toHaveBeenCalled();
});

test('fails closed when immutable metadata lacks the canonical or displayed source', async () => {
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never);
  vi.mocked(attachLabelmap).mockResolvedValue(editableLabelmap());
  vi.mocked(api.getCase).mockResolvedValueOnce(caseDetail([source('ADC'), source('FLAIR')]))
    .mockResolvedValueOnce(caseDetail([source('DWI'), source('ADC')]));
  const { rerender } = render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);
  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();

  rerender(<ViewerGrid selectedCase={selectedCase} modality="FLAIR" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);
  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  expect(attachLabelmap).not.toHaveBeenCalled();
});

test('fails closed when immutable source metadata is missing, duplicated, or malformed', async () => {
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never);
  vi.mocked(attachLabelmap).mockResolvedValue(editableLabelmap());
  vi.mocked(api.getCase).mockResolvedValueOnce(caseDetail([source('DWI'), source('DWI'), source('FLAIR')]))
    .mockResolvedValueOnce(caseDetail([source('DWI'), source('ADC'), { ...source('FLAIR'), affine: [[1, 0, 0, 0]] }]));
  const { rerender } = render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);
  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  expect(attachLabelmap).not.toHaveBeenCalled();

  rerender(<ViewerGrid selectedCase={selectedCase} modality="FLAIR" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);
  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  expect(attachLabelmap).not.toHaveBeenCalled();
});

test('removes a stale overlay on an authoritative matching-to-mismatched-to-matching modality transition', async () => {
  const first = editableLabelmap('first');
  const second = editableLabelmap('second');
  vi.mocked(createViewerSession).mockImplementation(() => Promise.resolve({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never));
  vi.mocked(api.getCase).mockResolvedValue(caseDetail());
  vi.mocked(attachLabelmap).mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  const onSegmentationChanged = vi.fn();
  const { rerender } = render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={onSegmentationChanged} />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalledTimes(1));

  rerender(<ViewerGrid selectedCase={selectedCase} modality="FLAIR" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={onSegmentationChanged} />);
  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  expect(first.destroy).toHaveBeenCalledTimes(1);
  expect(attachLabelmap).toHaveBeenCalledTimes(1);

  rerender(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={onSegmentationChanged} />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalledTimes(2));
  expect(onSegmentationChanged).toHaveBeenLastCalledWith(second);
});

test('ignores stale case-detail metadata after a modality transition', async () => {
  let resolveDwi!: (detail: CaseDetail) => void;
  const staleDwi = new Promise<CaseDetail>((resolve) => { resolveDwi = resolve; });
  vi.mocked(createViewerSession).mockImplementation(() => Promise.resolve({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never));
  vi.mocked(api.getCase).mockImplementationOnce(() => staleDwi).mockResolvedValueOnce(caseDetail());
  vi.mocked(attachLabelmap).mockResolvedValue(editableLabelmap());
  const { rerender } = render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);

  await waitFor(() => expect(api.getCase).toHaveBeenCalledTimes(1));
  rerender(<ViewerGrid selectedCase={selectedCase} modality="FLAIR" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);
  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  await act(async () => { resolveDwi(caseDetail([source('DWI'), source('ADC'), source('FLAIR', authoritativeDwi)])); });
  expect(attachLabelmap).not.toHaveBeenCalled();
});
