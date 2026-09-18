import { describe, expect, test } from 'vitest';
import { canDisplaySegmentationOn, type VolumeGeometry } from '../src/cornerstone/segmentation';

const dwi: VolumeGeometry = {
  shape: [64, 64, 24],
  affine: [[1, 0, 0, -32], [0, 1, 0, -32], [0, 0, 5, -60], [0, 0, 0, 1]],
};

describe('canDisplaySegmentationOn', () => {
  test('shows DWI-space masks only on matching geometry', () => {
    expect(canDisplaySegmentationOn(dwi, dwi)).toBe(true);
  });

  test('rejects a different source shape', () => {
    expect(canDisplaySegmentationOn({ ...dwi, shape: [64, 64, 25] }, dwi)).toBe(false);
  });

  test('accepts affine differences within 1e-5 and rejects greater differences', () => {
    const withinTolerance = { ...dwi, affine: dwi.affine.map((row) => [...row]) };
    withinTolerance.affine[0][1] = 0.00001;
    const outsideTolerance = { ...dwi, affine: dwi.affine.map((row) => [...row]) };
    outsideTolerance.affine[0][1] = 0.00001001;
    expect(canDisplaySegmentationOn(withinTolerance, dwi)).toBe(true);
    expect(canDisplaySegmentationOn(outsideTolerance, dwi)).toBe(false);
  });

  test('fails closed for malformed or non-finite affines', () => {
    expect(canDisplaySegmentationOn({ ...dwi, affine: [[1, 0, 0, 0]] }, dwi)).toBe(false);
    const nonFinite = { ...dwi, affine: dwi.affine.map((row) => [...row]) };
    nonFinite.affine[0][0] = Number.NaN;
    expect(canDisplaySegmentationOn(nonFinite, dwi)).toBe(false);
  });
});
