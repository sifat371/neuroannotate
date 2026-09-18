import { expect, test } from 'vitest';
import { createWorkspaceStore } from '../src/state/workspace';

test('tracks annotation dirty state explicitly', () => {
  const store = createWorkspaceStore();

  store.getState().markDirty();

  expect(store.getState().dirty).toBe(true);
});

test('clears annotation state when selecting another case', () => {
  const store = createWorkspaceStore();
  store.getState().setSelectedCaseId('case-1');
  store.getState().loadSegmentation('seg-1');
  store.getState().loadRevision('revision-1');
  store.getState().markDirty();
  store.getState().setActiveJobId('job-1');

  store.getState().setSelectedCaseId('case-2');

  expect(store.getState()).toMatchObject({
    selectedCaseId: 'case-2',
    loadedSegmentationId: null,
    loadedRevisionId: null,
    baseRevisionId: null,
    dirty: false,
    activeJobId: null,
  });
});
