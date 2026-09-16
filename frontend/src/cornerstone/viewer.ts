import {
  Enums,
  RenderingEngine,
  cache,
  setVolumesForViewports,
  volumeLoader,
} from '@cornerstonejs/core';
import * as cornerstoneTools from '@cornerstonejs/tools';
import { createNiftiImageIdsAndCacheMetadata } from '@cornerstonejs/nifti-volume-loader';
import { initializeCornerstone } from './init';

const { PanTool, ZoomTool, WindowLevelTool, StackScrollTool, ToolGroupManager, Enums: ToolEnums } = cornerstoneTools;
const { MouseBindings } = ToolEnums;
const toolClasses = [PanTool, ZoomTool, WindowLevelTool, StackScrollTool];
let toolsRegistered = false;

export const VIEWPORT_IDS = ['AXIAL', 'SAGITTAL', 'CORONAL'] as const;
export type ViewportId = typeof VIEWPORT_IDS[number];

export type ViewerSession = {
  id: string;
  caseId: string;
  modality: string;
  sourceVolumeId: string;
  renderingEngineId: string;
  toolGroupId: string;
  renderingEngine: RenderingEngine;
  setPrimaryTool: (toolName: string | null) => void;
  destroy: () => void;
};

type Elements = Record<ViewportId, HTMLDivElement>;

function registerTools() {
  if (toolsRegistered) return;
  for (const ToolClass of toolClasses) cornerstoneTools.addTool(ToolClass);
  toolsRegistered = true;
}

export async function createViewerSession({
  caseId,
  modality,
  elements,
  modalityUrl,
}: {
  caseId: string;
  modality: string;
  elements: Elements;
  modalityUrl: string;
}): Promise<ViewerSession> {
  await initializeCornerstone();
  registerTools();
  const id = `${caseId}-${modality}-${crypto.randomUUID()}`;
  const renderingEngineId = `render-${id}`;
  const toolGroupId = `tools-${id}`;
  const sourceVolumeId = `cornerstoneStreamingImageVolume:source-${id}`;
  const imageIds = await createNiftiImageIdsAndCacheMetadata({ url: modalityUrl });
  const volume = await volumeLoader.createAndCacheVolume(sourceVolumeId, { imageIds });
  await volume.load();

  const renderingEngine = new RenderingEngine(renderingEngineId);
  renderingEngine.setViewports([
    { viewportId: 'AXIAL', type: Enums.ViewportType.ORTHOGRAPHIC, element: elements.AXIAL, defaultOptions: { orientation: Enums.OrientationAxis.AXIAL } },
    { viewportId: 'SAGITTAL', type: Enums.ViewportType.ORTHOGRAPHIC, element: elements.SAGITTAL, defaultOptions: { orientation: Enums.OrientationAxis.SAGITTAL } },
    { viewportId: 'CORONAL', type: Enums.ViewportType.ORTHOGRAPHIC, element: elements.CORONAL, defaultOptions: { orientation: Enums.OrientationAxis.CORONAL } },
  ]);

  const group = ToolGroupManager.createToolGroup(toolGroupId);
  if (!group) throw new Error('Could not create Cornerstone tool group.');
  [WindowLevelTool, PanTool, ZoomTool, StackScrollTool].forEach((ToolClass) => group.addTool(ToolClass.toolName));
  VIEWPORT_IDS.forEach((viewportId) => group.addViewport(viewportId, renderingEngineId));
  group.setToolActive(WindowLevelTool.toolName, { bindings: [{ mouseButton: MouseBindings.Primary }] });
  group.setToolActive(ZoomTool.toolName, { bindings: [{ mouseButton: MouseBindings.Secondary }] });
  group.setToolActive(PanTool.toolName, { bindings: [{ mouseButton: MouseBindings.Auxiliary }] });
  group.setToolActive(StackScrollTool.toolName, { bindings: [{ mouseButton: MouseBindings.Wheel }] });

  await setVolumesForViewports(renderingEngine, [{ volumeId: sourceVolumeId }], [...VIEWPORT_IDS]);
  renderingEngine.render();

  const primaryTools = [WindowLevelTool.toolName, PanTool.toolName, ZoomTool.toolName];
  const setPrimaryTool = (toolName: string | null) => {
    primaryTools.forEach((name) => group.setToolPassive(name));
    if (toolName) {
      group.setToolActive(toolName, { bindings: [{ mouseButton: MouseBindings.Primary }] });
    }
  };

  return {
    id,
    caseId,
    modality,
    sourceVolumeId,
    renderingEngineId,
    toolGroupId,
    renderingEngine,
    setPrimaryTool,
    destroy() {
      ToolGroupManager.destroyToolGroup(toolGroupId);
      renderingEngine.destroy();
      cache.removeVolumeLoadObject(sourceVolumeId);
    },
  };
}
