import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { AnnotationToolbar } from '../src/features/annotation/AnnotationToolbar';

test('applies the selected brush size to the editable brush and eraser configuration', () => {
  const segmentation = {
    segmentationId: 'seg-1', volumeId: 'vol-1', sourceInferenceId: 'job-1', visible: true, opacity: 0.5, dirty: false, editCount: 0,
    setEditingTool: vi.fn(), setBrushSize: vi.fn(), undo: vi.fn(), redo: vi.fn(),
    getCurrentLabelmap: () => ({ shape: [1, 1, 1] as [number, number, number], voxels: new Uint8Array([0]) }),
    markSaved: vi.fn().mockReturnValue(true), replaceFromLabelmap: vi.fn(), replaceFromNifti: vi.fn(), destroy: vi.fn(),
  };
  render(<AnnotationToolbar segmentation={segmentation} activeTool="brush" onToolChange={() => undefined} />);
  fireEvent.change(screen.getByLabelText('Brush size'), { target: { value: '19' } });
  expect(segmentation.setBrushSize).toHaveBeenLastCalledWith(19);
});
