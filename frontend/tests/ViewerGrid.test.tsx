import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';

vi.mock('../src/cornerstone/viewer', () => ({
  createViewerSession: vi.fn().mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() }),
  getVolumeGeometry: vi.fn(),
}));
vi.mock('../src/cornerstone/segmentation', async (importOriginal) => ({
  ...await importOriginal<typeof import('../src/cornerstone/segmentation')>(),
  attachLabelmap: vi.fn(),
  setOverlayVisible: vi.fn(),
  setOverlayOpacity: vi.fn(),
}));

import { ViewerGrid } from '../src/features/viewer/ViewerGrid';
import { attachLabelmap } from '../src/cornerstone/segmentation';
import { createViewerSession, getVolumeGeometry } from '../src/cornerstone/viewer';

const dwiGeometry = {
  shape: [64, 64, 24] as [number, number, number],
  affine: [[1, 0, 0, -32], [0, 1, 0, -32], [0, 0, 5, -60], [0, 0, 0, 1]],
};
const flairGeometry = { ...dwiGeometry, affine: [[1, 0, 0, -32], [0, 1, 0, -32], [0, 0, 5, -55], [0, 0, 0, 1]] };
const selectedCase = { id: 'case-1', name: 'Case one', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true };

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
  vi.mocked(getVolumeGeometry).mockReset();
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
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn(), geometry: dwiGeometry } as never);
  vi.mocked(getVolumeGeometry).mockResolvedValue(dwiGeometry);
  const { rerender } = render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} revisionUrl="/old-revision.nii.gz" overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  rerender(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} revisionUrl="/latest-revision.nii.gz" overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalled());
  await act(async () => { resolveLabelmap(labelmap); });
  await waitFor(() => expect(labelmap.replaceFromNifti).toHaveBeenCalledWith('/latest-revision.nii.gz', expect.any(Function)));
  expect(labelmap.replaceFromNifti).toHaveBeenCalledTimes(1);
});

test('does not attach or expose an editable labelmap on a mismatched source geometry', async () => {
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn(), geometry: flairGeometry } as never);
  vi.mocked(getVolumeGeometry).mockResolvedValue(dwiGeometry);
  vi.mocked(attachLabelmap).mockResolvedValue(editableLabelmap());
  render(<ViewerGrid selectedCase={selectedCase} modality="FLAIR" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);

  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  expect(attachLabelmap).not.toHaveBeenCalled();
});

test('removes a stale overlay on a matching-to-mismatched-to-matching modality transition', async () => {
  const first = editableLabelmap('first');
  const second = editableLabelmap('second');
  vi.mocked(createViewerSession).mockImplementation(({ modality }) => Promise.resolve({
    destroy: vi.fn(), setPrimaryTool: vi.fn(), geometry: modality === 'FLAIR' ? flairGeometry : dwiGeometry,
  } as never));
  vi.mocked(getVolumeGeometry).mockResolvedValue(dwiGeometry);
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
