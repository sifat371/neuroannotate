export type SerializedLabelmap = {
  shape: [number, number, number];
  voxels: Uint8Array;
};

export function serializeLabelmap(
  scalarData: ArrayLike<number>,
  dimensions: readonly number[],
): SerializedLabelmap {
  if (dimensions.length !== 3 || dimensions.some((value) => !Number.isInteger(value) || value <= 0)) {
    throw new Error('Labelmap dimensions must contain exactly three positive integers.');
  }
  const shape: [number, number, number] = [dimensions[0], dimensions[1], dimensions[2]];
  const expected = shape[0] * shape[1] * shape[2];
  if (scalarData.length !== expected) {
    throw new Error(`Labelmap buffer length ${scalarData.length} does not match shape ${shape.join('x')}.`);
  }
  const voxels = new Uint8Array(expected);
  for (let index = 0; index < expected; index += 1) {
    voxels[index] = Number(scalarData[index]) === 0 ? 0 : 1;
  }
  return { shape, voxels };
}


export function toNiftiVoxelOrder(
  labelmap: SerializedLabelmap,
): SerializedLabelmap {
  const [sizeX, sizeY, sizeZ] = labelmap.shape;
  const sliceSize = sizeX * sizeY;
  const expected = sliceSize * sizeZ;

  if (labelmap.voxels.length !== expected) {
    throw new Error(
      `Labelmap buffer length ${labelmap.voxels.length} does not match shape ${labelmap.shape.join('x')}.`,
    );
  }

  /*
   * Cornerstone's NIfTI volume representation exposes the labelmap with the
   * slice index reversed relative to the NIfTI voxel array. Keep that layout
   * internally for rendering/editing, but restore NIfTI slice order at the
   * persistence boundary.
   */
  const voxels = new Uint8Array(expected);

  for (let sourceZ = 0; sourceZ < sizeZ; sourceZ += 1) {
    const sourceOffset = sourceZ * sliceSize;
    const destinationZ = sizeZ - 1 - sourceZ;
    const destinationOffset = destinationZ * sliceSize;

    voxels.set(
      labelmap.voxels.subarray(sourceOffset, sourceOffset + sliceSize),
      destinationOffset,
    );
  }

  return {
    shape: [...labelmap.shape],
    voxels,
  };
}
