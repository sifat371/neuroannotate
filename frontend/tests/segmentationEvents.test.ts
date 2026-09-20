import { describe, expect, test } from 'vitest';

import { isUserSegmentationEditEvent } from '../src/cornerstone/segmentationEvents';

describe('segmentation edit event classification', () => {
  test('ignores render-only segmentation modified events', () => {
    expect(isUserSegmentationEditEvent(
      { segmentationId: 'seg-1' },
      'seg-1',
    )).toBe(false);

    expect(isUserSegmentationEditEvent(
      { segmentationId: 'seg-1', modifiedSlicesToUse: [] },
      'seg-1',
    )).toBe(false);
  });

  test('ignores modified-slice events for another segmentation', () => {
    expect(isUserSegmentationEditEvent(
      { segmentationId: 'seg-other', modifiedSlicesToUse: [4], segmentIndex: 1 },
      'seg-1',
    )).toBe(false);
  });

  test('accepts real voxel-edit events with modified slices', () => {
    expect(isUserSegmentationEditEvent(
      { segmentationId: 'seg-1', modifiedSlicesToUse: [4], segmentIndex: 1 },
      'seg-1',
    )).toBe(true);

    expect(isUserSegmentationEditEvent(
      { segmentationId: 'seg-1', modifiedSlicesToUse: [2, 3, 4] },
      'seg-1',
    )).toBe(true);
  });
});
