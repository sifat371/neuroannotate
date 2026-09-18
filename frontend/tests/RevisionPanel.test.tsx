import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { RevisionPanel } from '../src/features/revisions/RevisionPanel';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, listRevisions: vi.fn(), saveRevision: vi.fn() } };
});

const segmentation = {
  segmentationId: 'seg-ui', volumeId: 'vol-ui', sourceInferenceId: 'job-1', visible: true, opacity: .55, dirty: true,
  setEditingTool: () => undefined, undo: () => undefined, redo: () => undefined,
  getCurrentLabelmap: () => ({ shape: [1, 1, 1] as [number, number, number], voxels: new Uint8Array([1]) }),
  markSaved: vi.fn(), replaceFromNifti: async () => undefined, destroy: () => undefined,
};
const revision = {
  id: 'rev-1', case_id: 'c1', source_inference_id: 'job-1', source_segmentation_id: 'seg-1', parent_revision_id: null,
  sha256: 'abc123', edit_stats: { added_voxels: 7, removed_voxels: 2 }, note: 'Corrected edge', created_at: '2026-09-17T12:00:00Z',
};

describe('RevisionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listRevisions).mockResolvedValue([revision]);
  });

test('save revision is disabled without an active segmentation', () => {
  render(<RevisionPanel caseId="c1" sourceInferenceId={null} segmentation={null} selectedRevisionId={null} dirty={false} onDirtyChange={() => undefined} onSelectedRevisionId={() => undefined} onLoadRevision={() => undefined} />);
  expect(screen.getByRole('button', { name: 'Save Revision' })).toBeDisabled();
});

  test('clears dirty state only after a revision persists and retains it after failure', async () => {
    const onDirtyChange = vi.fn();
    vi.mocked(api.saveRevision).mockResolvedValue(revision);
    const { rerender } = render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId={null} dirty onDirtyChange={onDirtyChange} onSelectedRevisionId={() => undefined} onLoadRevision={() => undefined} />);
    await userEvent.click(screen.getByRole('button', { name: 'Save Revision' }));
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(false));
    expect(segmentation.markSaved).toHaveBeenCalledTimes(1);

    onDirtyChange.mockClear();
    vi.mocked(api.saveRevision).mockRejectedValue(new Error('offline'));
    rerender(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId={null} dirty onDirtyChange={onDirtyChange} onSelectedRevisionId={() => undefined} onLoadRevision={() => undefined} />);
    await userEvent.click(screen.getByRole('button', { name: 'Save Revision' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/could not save revision/i));
    expect(onDirtyChange).not.toHaveBeenCalledWith(false);
  });

  test('shows AI-rooted lineage and does not discard dirty edits without confirmation', async () => {
    const onSelected = vi.fn();
    const onLoad = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId="rev-1" dirty onDirtyChange={() => undefined} onSelectedRevisionId={onSelected} onLoadRevision={onLoad} />);
    expect(await screen.findByText(/Added 7/)).toHaveTextContent('Added 7 · Removed 2');
    expect(screen.getAllByText(/AI segmentation/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/Base: AI segmentation/i)).not.toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: /revision 1/i }));
    expect(onSelected).not.toHaveBeenCalled();
    expect(onLoad).not.toHaveBeenCalled();
  });
});
