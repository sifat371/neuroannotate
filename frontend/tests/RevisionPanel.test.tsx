import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { RevisionPanel } from '../src/features/revisions/RevisionPanel';
import type { EditableSegmentation } from '../src/cornerstone/segmentation';
import type { Revision } from '../src/types/api';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, listRevisions: vi.fn(), saveRevision: vi.fn() } };
});

const revision: Revision = {
  id: 'rev-1', case_id: 'c1', source_inference_id: 'job-1', source_segmentation_id: 'seg-1', parent_revision_id: null,
  sha256: 'abc123', edit_stats: { added_voxels: 7, removed_voxels: 2 }, note: 'Corrected edge', created_at: '2026-09-17T12:00:00Z',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function editableSegmentation(options: { editCount?: number; dirty?: boolean } = {}): EditableSegmentation & { setEditCount: (value: number) => void } {
  let editCount = options.editCount ?? 1;
  let dirty = options.dirty ?? true;
  const markSaved = vi.fn((expected = editCount) => {
    if (editCount !== expected) {
      editCount = Math.max(1, editCount - expected);
      dirty = true;
      return false;
    }
    editCount = 0;
    dirty = false;
    return true;
  });
  return {
    segmentationId: 'seg-ui', volumeId: 'vol-ui', sourceInferenceId: 'job-1', visible: true, opacity: .55,
    get dirty() { return dirty; }, get editCount() { return editCount; },
    setEditCount(value: number) { editCount = value; dirty = value > 0; },
    setEditingTool: vi.fn(), setBrushSize: vi.fn(), undo: vi.fn(), redo: vi.fn(),
    getCurrentLabelmap: () => ({ shape: [1, 1, 1], voxels: new Uint8Array([1]) }),
    markSaved, replaceFromLabelmap: vi.fn(), replaceFromNifti: vi.fn().mockResolvedValue(true), destroy: vi.fn(),
  };
}

describe('RevisionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listRevisions).mockResolvedValue([revision]);
  });

  test('save revision is disabled without an active segmentation', () => {
    render(<RevisionPanel caseId="c1" sourceInferenceId={null} segmentation={null} selectedRevisionId={null} dirty={false} onDirtyChange={() => undefined} onRevisionSaved={() => undefined} onRevisionLoaded={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Save Revision' })).toBeDisabled();
  });

  test('clears dirty state only after the exact saved edit generation persists', async () => {
    const segmentation = editableSegmentation();
    const onDirtyChange = vi.fn();
    const onRevisionSaved = vi.fn();
    vi.mocked(api.saveRevision).mockResolvedValue(revision);
    render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId={null} dirty onDirtyChange={onDirtyChange} onRevisionSaved={onRevisionSaved} onRevisionLoaded={() => undefined} />);
    await userEvent.click(screen.getByRole('button', { name: 'Save Revision' }));
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(false));
    expect(segmentation.markSaved).toHaveBeenCalledWith(1);
    expect(onRevisionSaved).toHaveBeenCalledWith(revision, true);
  });

  test('retains edits made while a save request is pending', async () => {
    const pending = deferred<Revision>();
    const segmentation = editableSegmentation({ editCount: 1 });
    const onDirtyChange = vi.fn();
    const onRevisionSaved = vi.fn();
    vi.mocked(api.saveRevision).mockReturnValue(pending.promise);
    render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId={null} dirty onDirtyChange={onDirtyChange} onRevisionSaved={onRevisionSaved} onRevisionLoaded={() => undefined} />);
    await userEvent.click(screen.getByRole('button', { name: 'Save Revision' }));
    segmentation.setEditCount(3);
    await act(async () => { pending.resolve(revision); });
    await waitFor(() => expect(onRevisionSaved).toHaveBeenCalledWith(revision, false));
    expect(segmentation.markSaved).toHaveBeenCalledWith(1);
    expect(onDirtyChange).toHaveBeenCalledWith(true);
    expect(segmentation.dirty).toBe(true);
    expect(segmentation.editCount).toBe(2);
  });

  test('ignores a save response after the selected case changes', async () => {
    const pending = deferred<Revision>();
    const segmentation = editableSegmentation();
    const onDirtyChange = vi.fn();
    const onRevisionSaved = vi.fn();
    vi.mocked(api.saveRevision).mockReturnValue(pending.promise);
    const { rerender } = render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId={null} dirty onDirtyChange={onDirtyChange} onRevisionSaved={onRevisionSaved} onRevisionLoaded={() => undefined} />);
    await userEvent.click(screen.getByRole('button', { name: 'Save Revision' }));
    rerender(<RevisionPanel caseId="c2" sourceInferenceId="job-2" segmentation={editableSegmentation()} selectedRevisionId={null} dirty={false} onDirtyChange={onDirtyChange} onRevisionSaved={onRevisionSaved} onRevisionLoaded={() => undefined} />);
    await act(async () => { pending.resolve(revision); });
    expect(onRevisionSaved).not.toHaveBeenCalled();
    expect(onDirtyChange).not.toHaveBeenCalledWith(false);
  });

  test('commits revision selection only after the mask loads successfully', async () => {
    const segmentation = editableSegmentation({ dirty: false, editCount: 0 });
    const onRevisionLoaded = vi.fn();
    const onPending = vi.fn();
    const pending = deferred<boolean>();
    vi.mocked(segmentation.replaceFromNifti).mockReturnValue(pending.promise);
    render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId={null} dirty={false} onDirtyChange={() => undefined} onRevisionSaved={() => undefined} onRevisionLoaded={onRevisionLoaded} onLoadPendingChange={onPending} />);
    const button = await screen.findByRole('button', { name: /revision 1/i });
    await userEvent.click(button);
    expect(onPending).toHaveBeenCalledWith(true);
    expect(onRevisionLoaded).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Save Revision' })).toBeDisabled();
    await act(async () => { pending.resolve(true); });
    await waitFor(() => expect(onRevisionLoaded).toHaveBeenCalledWith(revision));
    expect(onPending).toHaveBeenLastCalledWith(false);
  });

  test('preserves the previous selection when a revision mask load fails', async () => {
    const segmentation = editableSegmentation({ dirty: false, editCount: 0 });
    vi.mocked(segmentation.replaceFromNifti).mockRejectedValue(new Error('broken mask'));
    const onRevisionLoaded = vi.fn();
    render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId={null} dirty={false} onDirtyChange={() => undefined} onRevisionSaved={() => undefined} onRevisionLoaded={onRevisionLoaded} />);
    await userEvent.click(await screen.findByRole('button', { name: /revision 1/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load revision/i);
    expect(onRevisionLoaded).not.toHaveBeenCalled();
  });

  test('ignores a delayed revision load and revision list after the case changes', async () => {
    const listC1 = deferred<Revision[]>();
    const listC2 = deferred<Revision[]>();
    vi.mocked(api.listRevisions).mockImplementation((caseId) => caseId === 'c1' ? listC1.promise : listC2.promise);
    const segmentation = editableSegmentation({ dirty: false, editCount: 0 });
    const replacement = deferred<boolean>();
    vi.mocked(segmentation.replaceFromNifti).mockImplementation(async (_url, shouldApply = () => true) => {
      await replacement.promise;
      return shouldApply();
    });
    const onRevisionLoaded = vi.fn();
    const { rerender } = render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId={null} dirty={false} onDirtyChange={() => undefined} onRevisionSaved={() => undefined} onRevisionLoaded={onRevisionLoaded} />);
    await act(async () => { listC1.resolve([revision]); });
    await userEvent.click(await screen.findByRole('button', { name: /revision 1/i }));
    rerender(<RevisionPanel caseId="c2" sourceInferenceId="job-2" segmentation={editableSegmentation({ dirty: false, editCount: 0 })} selectedRevisionId={null} dirty={false} onDirtyChange={() => undefined} onRevisionSaved={() => undefined} onRevisionLoaded={onRevisionLoaded} />);
    await act(async () => {
      listC2.resolve([{ ...revision, id: 'rev-c2', case_id: 'c2' }]);
      replacement.resolve(true);
    });
    expect(onRevisionLoaded).not.toHaveBeenCalled();
    expect(await screen.findByRole('button', { name: /revision 1/i })).toHaveTextContent('Revision 1');
  });

  test('does not discard dirty edits without confirmation', async () => {
    const segmentation = editableSegmentation();
    const onRevisionLoaded = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<RevisionPanel caseId="c1" sourceInferenceId="job-1" segmentation={segmentation} selectedRevisionId="rev-1" dirty onDirtyChange={() => undefined} onRevisionSaved={() => undefined} onRevisionLoaded={onRevisionLoaded} />);
    expect(await screen.findByText(/Added 7/)).toHaveTextContent('Added 7 · Removed 2');
    await userEvent.click(screen.getByRole('button', { name: /revision 1/i }));
    expect(onRevisionLoaded).not.toHaveBeenCalled();
    expect(segmentation.replaceFromNifti).not.toHaveBeenCalled();
  });
});
