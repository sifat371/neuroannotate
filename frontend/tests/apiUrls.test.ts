import { expect, test } from 'vitest';
import { api, segmentationFileUrl } from '../src/api/client';

test('NIfTI download URLs retain a .nii.gz suffix for Cornerstone', () => {
  expect(api.getModalityFileUrl('case-1', 'DWI')).toMatch(/\/file\.nii\.gz$/);
  expect(api.getLatestSegmentationFileUrl('case-1')).toMatch(/\/file\.nii\.gz$/);
  expect(api.getRevisionFileUrl('case-1', 'revision-1')).toMatch(/\/file\.nii\.gz$/);
});

test('keeps a .nii.gz suffix for Cornerstone segmentation URLs', () => {
  expect(segmentationFileUrl('seg-1')).toMatch(/\/api\/segmentations\/seg-1\/file\.nii\.gz$/);
});
