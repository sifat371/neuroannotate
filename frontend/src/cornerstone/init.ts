import { imageLoader, init as initCore } from '@cornerstonejs/core';
import { init as initTools } from '@cornerstonejs/tools';
import { cornerstoneNiftiImageLoader } from '@cornerstonejs/nifti-volume-loader';

let initialization: Promise<void> | null = null;

export function initializeCornerstone(): Promise<void> {
  if (!initialization) {
    initialization = (async () => {
      await initCore();
      initTools();
      imageLoader.registerImageLoader('nifti', cornerstoneNiftiImageLoader);
    })();
  }
  return initialization;
}
