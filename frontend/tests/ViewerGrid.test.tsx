import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

vi.mock('../src/cornerstone/viewer', () => ({
  createViewerSession: vi.fn().mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() }),
}));
vi.mock('../src/cornerstone/segmentation', () => ({
  attachLabelmap: vi.fn(), setOverlayVisible: vi.fn(), setOverlayOpacity: vi.fn(),
}));

import { ViewerGrid } from '../src/features/viewer/ViewerGrid';

test('mounts all three orthogonal viewport containers', () => {
  render(<ViewerGrid selectedCase={null} modality="DWI" inference={null} overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  expect(screen.getByLabelText('Axial MRI viewport')).toBeInTheDocument();
  expect(screen.getByLabelText('Sagittal MRI viewport')).toBeInTheDocument();
  expect(screen.getByLabelText('Coronal MRI viewport')).toBeInTheDocument();
});
