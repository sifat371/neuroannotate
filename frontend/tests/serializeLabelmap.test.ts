import { describe, expect, test } from 'vitest';
import {
  serializeLabelmap,
  toNiftiVoxelOrder,
} from '../src/cornerstone/serializeLabelmap';

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

  test('restores NIfTI Z-slice order at the persistence boundary', () => {
    const cornerstone = {
      shape: [2, 2, 3] as [number, number, number],
      voxels: new Uint8Array([
        // Cornerstone Z0
        1, 0, 0, 0,
        // Cornerstone Z1
        0, 1, 0, 0,
        // Cornerstone Z2
        0, 0, 1, 0,
      ]),
    };

    const result = toNiftiVoxelOrder(cornerstone);

    expect(result.shape).toEqual([2, 2, 3]);
    expect(Array.from(result.voxels)).toEqual([
      // NIfTI Z0 <- Cornerstone Z2
      0, 0, 1, 0,
      // NIfTI Z1 <- Cornerstone Z1
      0, 1, 0, 0,
      // NIfTI Z2 <- Cornerstone Z0
      1, 0, 0, 0,
    ]);
  });

  test('NIfTI slice-order conversion is its own inverse', () => {
    const original = {
      shape: [2, 2, 3] as [number, number, number],
      voxels: new Uint8Array([
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
      ]),
    };

    const roundTrip = toNiftiVoxelOrder(toNiftiVoxelOrder(original));

    expect(Array.from(roundTrip.voxels)).toEqual(Array.from(original.voxels));
  });

  test('rejects non-3D dimensions', () => {
    expect(() => serializeLabelmap(new Uint8Array([1, 0]), [2, 1])).toThrow(/three/);
  });
});
