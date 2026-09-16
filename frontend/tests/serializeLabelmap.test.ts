import { describe, expect, test } from 'vitest';
import { serializeLabelmap } from '../src/cornerstone/serializeLabelmap';

describe('serializeLabelmap', () => {
  test('preserves Cornerstone x-fastest voxel ordering', () => {
    const input = new Uint8Array([1, 0, 0, 0, 0, 1]);
    const result = serializeLabelmap(input, [3, 2, 1]);
    expect(result.shape).toEqual([3, 2, 1]);
    expect(Array.from(result.voxels)).toEqual([1, 0, 0, 0, 0, 1]);
  });

  test('normalizes every nonzero value to one', () => {
    const result = serializeLabelmap(new Int16Array([0, 2, -4, 1]), [2, 2, 1]);
    expect(Array.from(result.voxels)).toEqual([0, 1, 1, 1]);
  });

  test('rejects non-3D dimensions', () => {
    expect(() => serializeLabelmap(new Uint8Array([1, 0]), [2, 1])).toThrow(/three/);
  });
});
