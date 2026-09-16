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

export type EditableSegmentation = {
  segmentationId: string;
  volumeId: string;
  sourceInferenceId: string;
  visible: boolean;
  opacity: number;
  dirty: boolean;
  setEditingTool: (tool: 'brush' | 'erase' | 'pan' | 'zoom' | 'windowLevel') => void;
  undo: () => void;
  redo: () => void;
  getCurrentLabelmap: () => SerializedLabelmap;
  markSaved: () => void;
  replaceFromNifti: (url: string) => Promise<void>;
  destroy: () => void;
};

function ensureBrushRegistered() {
  if (!brushRegistered) {
    cornerstoneTools.addTool(BrushTool);
    brushRegistered = true;
  }
}

function copyIntoLabelmap(volumeId: string, sourceData: ArrayLike<number>) {
  const destination = cache.getVolume(volumeId);
  if (!destination?.voxelManager) throw new Error('Editable labelmap volume is unavailable.');
  const expected = destination.dimensions.reduce((total: number, value: number) => total * value, 1);
  if (sourceData.length !== expected) throw new Error('Segmentation geometry does not match the active MRI volume.');
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
  let visible = true;
  let opacity = 0.55;

  const dataModified = (event: Event) => {
    const detail = (event as CustomEvent<{ segmentationId?: string }>).detail;
    if (detail?.segmentationId === segmentationId) dirty = true;
  };
  eventTarget.addEventListener(ToolEnums.Events.SEGMENTATION_DATA_MODIFIED, dataModified);

  const api: EditableSegmentation = {
    segmentationId,
    volumeId,
    sourceInferenceId,
    get visible() { return visible; },
    get opacity() { return opacity; },
    get dirty() { return dirty; },
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
    undo() {
      DefaultHistoryMemo.undo();
      dirty = true;
    },
    redo() {
      DefaultHistoryMemo.redo();
      dirty = true;
    },
    getCurrentLabelmap() {
      const volume = cache.getVolume(volumeId);
      const voxelManager = volume?.voxelManager;
      if (!volume || !voxelManager?.getCompleteScalarDataArray) {
        throw new Error('Editable segmentation is unavailable.');
      }
      return serializeLabelmap(voxelManager.getCompleteScalarDataArray(), volume.dimensions);
    },
    markSaved() { dirty = false; },
    async replaceFromNifti(url) {
      const replacement = await loadMaskData(url, segmentationId);
      copyIntoLabelmap(volumeId, replacement);
      segmentation.triggerSegmentationEvents.triggerSegmentationDataModified(segmentationId);
      dirty = false;
      session.renderingEngine.render();
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
