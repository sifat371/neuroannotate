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
