import { act, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

vi.mock('../src/cornerstone/viewer', () => ({
  createViewerSession: vi.fn().mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() }),
}));
vi.mock('../src/cornerstone/segmentation', () => ({
  attachLabelmap: vi.fn(), setOverlayVisible: vi.fn(), setOverlayOpacity: vi.fn(),
}));

import { ViewerGrid } from '../src/features/viewer/ViewerGrid';
import { attachLabelmap } from '../src/cornerstone/segmentation';

test('mounts all three orthogonal viewport containers', () => {
  render(<ViewerGrid selectedCase={null} modality="DWI" inference={null} overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  expect(screen.getByLabelText('Axial MRI viewport')).toBeInTheDocument();
  expect(screen.getByLabelText('Sagittal MRI viewport')).toBeInTheDocument();
  expect(screen.getByLabelText('Coronal MRI viewport')).toBeInTheDocument();
});

test('applies the latest revision selected before its editable labelmap becomes ready', async () => {
  let resolveLabelmap!: (value: import('../src/cornerstone/segmentation').EditableSegmentation) => void;
  const labelmap = {
    segmentationId: 'seg-ui', volumeId: 'vol-ui', sourceInferenceId: 'job-1', visible: true, opacity: 0.5, dirty: false, editCount: 0,
    setEditingTool: vi.fn(), setBrushSize: vi.fn(), undo: vi.fn(), redo: vi.fn(),
    getCurrentLabelmap: () => ({ shape: [1, 1, 1] as [number, number, number], voxels: new Uint8Array([0]) }),
    markSaved: vi.fn(), replaceFromNifti: vi.fn().mockResolvedValue(true), destroy: vi.fn(),
  };
  vi.mocked(attachLabelmap).mockImplementationOnce(() => new Promise((resolve) => { resolveLabelmap = resolve; }));
  const selectedCase = { id: 'case-1', name: 'Case one', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true };
  const { rerender } = render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} revisionUrl="/old-revision.nii.gz" overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  rerender(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} revisionUrl="/latest-revision.nii.gz" overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalled());
  await act(async () => { resolveLabelmap(labelmap); });
  await waitFor(() => expect(labelmap.replaceFromNifti).toHaveBeenCalledWith('/latest-revision.nii.gz', expect.any(Function)));
  expect(labelmap.replaceFromNifti).toHaveBeenCalledTimes(1);
});
