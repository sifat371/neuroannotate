import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

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

function migratedSource(modality: SourceArtifact['modality']): SourceArtifact {
  return { ...source(modality), sha256: null, file_size: null, datatype: null };
}

function caseDetail(sources: SourceArtifact[] = [source('DWI'), source('ADC'), source('FLAIR', authoritativeFlair)]): CaseDetail {
  return { ...selectedCase, annotation_space: 'DWI', sources };
}

function editableLabelmap(id = 'seg-ui', options: { dirty?: boolean; editCount?: number; voxel?: number } = {}) {
  const labelmap = { shape: [1, 1, 1] as [number, number, number], voxels: new Uint8Array([options.voxel ?? 0]) };
  return {
    segmentationId: id, volumeId: `vol-${id}`, sourceInferenceId: 'job-1', visible: true, opacity: 0.5,
    dirty: options.dirty ?? false, editCount: options.editCount ?? 0,
    setEditingTool: vi.fn(), setBrushSize: vi.fn(), undo: vi.fn(), redo: vi.fn(),
    getCurrentLabelmap: vi.fn(() => labelmap),
    markSaved: vi.fn().mockReturnValue(true), replaceFromLabelmap: vi.fn(), replaceFromNifti: vi.fn().mockResolvedValue(true), destroy: vi.fn(),
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

test('loads the current saved base mask when creating an editable labelmap', async () => {
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never);
  vi.mocked(api.getCase).mockResolvedValue(caseDetail([source('DWI'), source('ADC'), source('FLAIR', authoritativeDwi)]));
  vi.mocked(attachLabelmap).mockResolvedValue(editableLabelmap());
  render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} baseMaskUrl="/revision-current.nii.gz" overlayVisible overlayOpacity={0.5} activeTool="windowLevel" onSegmentationChanged={() => undefined} />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalledWith(expect.anything(), '/revision-current.nii.gz', 'job-1', undefined));
});

test('uses authoritative anisotropic oblique and sheared metadata rather than normalized display geometry', async () => {
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never);
  vi.mocked(api.getCase).mockResolvedValue(caseDetail());
  vi.mocked(attachLabelmap).mockResolvedValue(editableLabelmap());
  render(<ViewerGrid selectedCase={selectedCase} modality="FLAIR" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);

  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  expect(attachLabelmap).not.toHaveBeenCalled();
});

test('uses migrated source geometry when legacy integrity metadata is unavailable', async () => {
  vi.mocked(createViewerSession).mockResolvedValue({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never);
  vi.mocked(api.getCase).mockResolvedValue(caseDetail([migratedSource('DWI'), migratedSource('ADC'), migratedSource('FLAIR')]));
  vi.mocked(attachLabelmap).mockResolvedValue(editableLabelmap());
  render(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);

  await waitFor(() => expect(attachLabelmap).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Segmentation overlay unavailable in this geometry.')).not.toBeInTheDocument();
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
  rerender(<ViewerGrid selectedCase={selectedCase} modality="FLAIR" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={() => undefined} />);
  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  expect(attachLabelmap).not.toHaveBeenCalled();
});

test('preserves dirty canonical mask bytes across matching-to-mismatched-to-matching modality changes', async () => {
  const first = editableLabelmap('first', { dirty: true, editCount: 4, voxel: 1 });
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

  rerender(<ViewerGrid selectedCase={selectedCase} modality="DWI" inference={{ sourceInferenceId: 'job-1', segmentationId: 'seg-1' }} overlayVisible overlayOpacity={0.5} activeTool="brush" onSegmentationChanged={onSegmentationChanged} />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalledTimes(2));
  expect(second.replaceFromLabelmap).toHaveBeenCalledWith(
    expect.objectContaining({ shape: [1, 1, 1], voxels: expect.any(Uint8Array) }),
    { dirty: true, editCount: 4 },
  );
  const restored = vi.mocked(second.replaceFromLabelmap).mock.calls[0][0];
  expect(Array.from(restored.voxels)).toEqual([1]);
});

test('uses the newest saved revision as the reattachment base after modality changes', async () => {
  const first = editableLabelmap('first', { dirty: false, voxel: 1 });
  const second = editableLabelmap('second');
  vi.mocked(createViewerSession).mockImplementation(() => Promise.resolve({ destroy: vi.fn(), setPrimaryTool: vi.fn() } as never));
  vi.mocked(api.getCase).mockResolvedValue(caseDetail());
  vi.mocked(attachLabelmap).mockResolvedValueOnce(first).mockResolvedValueOnce(second);
  const common = { selectedCase, inference: { sourceInferenceId: 'job-1', segmentationId: 'seg-1' }, overlayVisible: true, overlayOpacity: 0.5, activeTool: 'brush' as const, onSegmentationChanged: () => undefined };
  const { rerender } = render(<ViewerGrid {...common} modality="DWI" baseMaskUrl="/revision-2.nii.gz" />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalledTimes(1));
  rerender(<ViewerGrid {...common} modality="FLAIR" baseMaskUrl="/revision-2.nii.gz" />);
  expect(await screen.findByText('Segmentation overlay unavailable in this geometry.')).toBeInTheDocument();
  rerender(<ViewerGrid {...common} modality="DWI" baseMaskUrl="/revision-2.nii.gz" />);
  await waitFor(() => expect(attachLabelmap).toHaveBeenCalledTimes(2));
  expect(vi.mocked(attachLabelmap).mock.calls[1][1]).toBe('/revision-2.nii.gz');
  expect(second.replaceFromLabelmap).toHaveBeenCalledWith(expect.anything(), { dirty: false, editCount: 0 });
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
