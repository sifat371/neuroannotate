import { expect, test } from 'vitest';
import { revisionFileUrl, segmentationFileUrl, sourceFileUrl } from '../src/api/client';

test('NIfTI download URLs retain a .nii.gz suffix for Cornerstone', () => {
  expect(sourceFileUrl('case-1', 'DWI')).toMatch(/\/file\.nii\.gz$/);
  expect(revisionFileUrl('revision-1')).toMatch(/\/file\.nii\.gz$/);
});

test('keeps a .nii.gz suffix for Cornerstone segmentation URLs', () => {
  expect(segmentationFileUrl('seg-1')).toMatch(/\/api\/segmentations\/seg-1\/file\.nii\.gz$/);
});
