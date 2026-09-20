import { cache, eventTarget, utilities as csUtils, volumeLoader } from '@cornerstonejs/core';
import * as cornerstoneTools from '@cornerstonejs/tools';
import { createNiftiImageIdsAndCacheMetadata } from '@cornerstonejs/nifti-volume-loader';
import type { ViewerSession } from './viewer';
import { VIEWPORT_IDS } from './viewer';
import { serializeLabelmap, type SerializedLabelmap } from './serializeLabelmap';
import { waitForVolumeLoad } from './volumeLoading';

const { BrushTool, ToolGroupManager, Enums: ToolEnums, segmentation } = cornerstoneTools;
const { MouseBindings, SegmentationRepresentations } = ToolEnums;
const { DefaultHistoryMemo } = csUtils.HistoryMemo;
let brushRegistered = false;

export interface VolumeGeometry {
  shape: [number, number, number];
  affine: number[][];
}

const AFFINE_TOLERANCE = 1e-5;

function isValidGeometry(geometry: VolumeGeometry): boolean {
  return Array.isArray(geometry?.shape)
    && geometry.shape.length === 3
    && geometry.shape.every((dimension) => Number.isInteger(dimension) && dimension > 0)
    && Array.isArray(geometry?.affine)
    && geometry.affine.length === 4
    && geometry.affine.every((row) => Array.isArray(row) && row.length === 4 && row.every(Number.isFinite));
}

export function canDisplaySegmentationOn(source: VolumeGeometry, dwi: VolumeGeometry): boolean {
  if (!isValidGeometry(source) || !isValidGeometry(dwi)) return false;
  return source.shape.every((dimension, index) => dimension === dwi.shape[index])
    && source.affine.every((row, rowIndex) => row.every(
      (value, columnIndex) => Math.abs(value - dwi.affine[rowIndex][columnIndex]) <= AFFINE_TOLERANCE,
    ));
}

export type EditableSegmentation = {
  segmentationId: string;
  volumeId: string;
  sourceInferenceId: string;
  visible: boolean;
  opacity: number;
  dirty: boolean;
  editCount: number;
  setEditingTool: (tool: 'brush' | 'erase' | 'pan' | 'zoom' | 'windowLevel') => void;
  setBrushSize: (size: number) => void;
  undo: () => void;
  redo: () => void;
  getCurrentLabelmap: () => SerializedLabelmap;
  markSaved: (expectedEditCount?: number) => boolean;
  replaceFromLabelmap: (data: SerializedLabelmap, state?: { dirty: boolean; editCount: number }) => void;
  replaceFromNifti: (url: string, shouldApply?: () => boolean) => Promise<boolean>;
  destroy: () => void;
};

function ensureBrushRegistered() {
  if (!brushRegistered) {
    cornerstoneTools.addTool(BrushTool);
    brushRegistered = true;
  }
}

function copyIntoLabelmap(volumeId: string, sourceData: ArrayLike<number>, sourceShape?: readonly number[]) {
  const destination = cache.getVolume(volumeId);
  if (!destination?.voxelManager) throw new Error('Editable labelmap volume is unavailable.');
  const expected = destination.dimensions.reduce((total: number, value: number) => total * value, 1);
  if (sourceData.length !== expected) throw new Error('Segmentation geometry does not match the active MRI volume.');
  if (sourceShape && (
    sourceShape.length !== 3
    || sourceShape.some((dimension, index) => dimension !== destination.dimensions[index])
  )) {
    throw new Error('Segmentation geometry does not match the active MRI volume.');
  }
  for (let index = 0; index < expected; index += 1) {
    destination.voxelManager.setAtIndex(index, Number(sourceData[index]) === 0 ? 0 : 1);
  }
}

async function loadMaskData(url: string, key: string): Promise<ArrayLike<number>> {
  const maskVolumeId = `cornerstoneStreamingImageVolume:mask-${key}-${crypto.randomUUID()}`;
  const imageIds = await createNiftiImageIdsAndCacheMetadata({ url });
  const volume = await volumeLoader.createAndCacheVolume(maskVolumeId, { imageIds });
  try {
    await waitForVolumeLoad(volume);
    const voxelManager = volume.voxelManager;
    if (!voxelManager?.getCompleteScalarDataArray) {
      throw new Error('Loaded segmentation volume does not expose scalar voxel data.');
    }
    return voxelManager.getCompleteScalarDataArray();
  } finally {
    cache.removeVolumeLoadObject(maskVolumeId);
  }
}

export async function attachLabelmap(
  session: ViewerSession,
  niftiUrl: string,
  sourceInferenceId: string,
  onEditStateChange?: (dirty: boolean, editCount: number) => void,
): Promise<EditableSegmentation> {
  ensureBrushRegistered();
  const segmentationId = `seg-${sourceInferenceId}-${crypto.randomUUID()}`;
  const volumeId = `labelmap-${segmentationId}`;
  const derived = await volumeLoader.createAndCacheDerivedLabelmapVolume(session.sourceVolumeId, { volumeId });
  void derived;
  const sourceData = await loadMaskData(niftiUrl, segmentationId);
  copyIntoLabelmap(volumeId, sourceData);

  segmentation.addSegmentations([{
    segmentationId,
    representation: { type: SegmentationRepresentations.Labelmap, data: { volumeId } },
  }]);
  await segmentation.addLabelmapRepresentationToViewportMap(Object.fromEntries(
    VIEWPORT_IDS.map((viewportId) => [viewportId, [{ segmentationId }]]),
  ));
  segmentation.segmentIndex.setActiveSegmentIndex(segmentationId, 1);
  VIEWPORT_IDS.forEach((viewportId) => segmentation.activeSegmentation.setActiveSegmentation(viewportId, segmentationId));
  segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(segmentationId);
  session.renderingEngine.render();

  const group = ToolGroupManager.getToolGroup(session.toolGroupId);
  if (!group) throw new Error('Cornerstone tool group is unavailable.');
  const brushName = `CircularBrush-${segmentationId}`;
  const eraserName = `CircularEraser-${segmentationId}`;
  group.addToolInstance(brushName, BrushTool.toolName, { activeStrategy: 'FILL_INSIDE_CIRCLE', preview: { enabled: false }, useCenterSegmentIndex: true });
  group.addToolInstance(eraserName, BrushTool.toolName, { activeStrategy: 'ERASE_INSIDE_CIRCLE', preview: { enabled: false } });
  group.setToolPassive(brushName);
  group.setToolPassive(eraserName);
  let dirty = false;
  let editCount = 0;
  let visible = true;
  let opacity = 0.55;
  let suppressDataModified = false;

  const notify = () => onEditStateChange?.(dirty, editCount);
  const dataModified = (event: Event) => {
    const detail = (event as CustomEvent<{ segmentationId?: string }>).detail;
    if (detail?.segmentationId === segmentationId && !suppressDataModified) {
      dirty = true;
      editCount += 1;
      notify();
    }
  };
  eventTarget.addEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, dataModified);

  function triggerProgrammaticUpdate() {
    suppressDataModified = true;
    try {
      segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(segmentationId);
    } finally {
      suppressDataModified = false;
    }
    session.renderingEngine.render();
  }

  const api: EditableSegmentation = {
    segmentationId,
    volumeId,
    sourceInferenceId,
    get visible() { return visible; },
    get opacity() { return opacity; },
    get dirty() { return dirty; },
    get editCount() { return editCount; },
    setEditingTool(tool) {
      group.setToolPassive(brushName);
      group.setToolPassive(eraserName);
      if (tool === 'brush') {
        session.setPrimaryTool(null);
        group.setToolActive(brushName, { bindings: [{ mouseButton: MouseBindings.Primary }] });
      } else if (tool === 'erase') {
        session.setPrimaryTool(null);
        group.setToolActive(eraserName, { bindings: [{ mouseButton: MouseBindings.Primary }] });
      }
      else {
        const map = { pan: 'Pan', zoom: 'Zoom', windowLevel: 'WindowLevel' } as const;
        session.setPrimaryTool(map[tool]);
      }
    },
    setBrushSize(size) {
      const brushSize = Math.max(1, Math.min(40, Math.round(size)));
      group.setToolConfiguration(brushName, { brushSize });
      group.setToolConfiguration(eraserName, { brushSize });
    },
    undo() {
      DefaultHistoryMemo.undo();
      dirty = true;
      editCount += 1;
      notify();
    },
    redo() {
      DefaultHistoryMemo.redo();
      dirty = true;
      editCount += 1;
      notify();
    },
    getCurrentLabelmap() {
      const volume = cache.getVolume(volumeId);
      const voxelManager = volume?.voxelManager;
      if (!volume || !voxelManager?.getCompleteScalarDataArray) {
        throw new Error('Editable segmentation is unavailable.');
      }
      return serializeLabelmap(voxelManager.getCompleteScalarDataArray(), volume.dimensions);
    },
    markSaved(expectedEditCount = editCount) {
      if (editCount !== expectedEditCount) {
        editCount = Math.max(1, editCount - expectedEditCount);
        dirty = true;
        notify();
        return false;
      }
      dirty = false;
      editCount = 0;
      notify();
      return true;
    },
    replaceFromLabelmap(data, state = { dirty: false, editCount: 0 }) {
      copyIntoLabelmap(volumeId, data.voxels, data.shape);
      triggerProgrammaticUpdate();
      dirty = state.dirty;
      editCount = state.editCount;
      notify();
    },
    async replaceFromNifti(url, shouldApply = () => true) {
      const replacement = await loadMaskData(url, segmentationId);
      if (!shouldApply()) return false;
      copyIntoLabelmap(volumeId, replacement);
      triggerProgrammaticUpdate();
      dirty = false;
      editCount = 0;
      notify();
      return true;
    },
    destroy() {
      eventTarget.removeEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, dataModified);
      segmentation.removeSegmentation(segmentationId);
      cache.removeVolumeLoadObject(volumeId);
    },
  };
  return api;
}

export function setOverlayVisible(seg: EditableSegmentation, visible: boolean) {
  for (const viewportId of VIEWPORT_IDS) {
    segmentation.config.visibility.setSegmentationRepresentationVisibility(
      viewportId,
      { segmentationId: seg.segmentationId, type: SegmentationRepresentations.Labelmap },
      visible,
    );
  }
  Object.defineProperty(seg, 'visible', { configurable: true, get: () => visible });
}

export function setOverlayOpacity(seg: EditableSegmentation, opacity: number) {
  const value = Math.min(1, Math.max(0, opacity));
  for (const viewportId of VIEWPORT_IDS) {
    segmentation.config.style.setStyle(
      { viewportId, segmentationId: seg.segmentationId, type: SegmentationRepresentations.Labelmap },
      { fillAlpha: value, outlineOpacity: Math.min(1, value + 0.2) },
    );
  }
  Object.defineProperty(seg, 'opacity', { configurable: true, get: () => value });
}
