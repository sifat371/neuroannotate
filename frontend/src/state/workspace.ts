import { create } from 'zustand';
import { createStore } from 'zustand/vanilla';
import type { StateCreator } from 'zustand/vanilla';
import type { Modality } from '../types/api';

export type EditingTool = 'brush' | 'erase' | 'pan' | 'zoom' | 'windowLevel';

export type WorkspaceState = {
  selectedCaseId: string | null;
  selectedModality: Modality;
  loadedSegmentationId: string | null;
  loadedRevisionId: string | null;
  baseRevisionId: string | null;
  dirty: boolean;
  activeJobId: string | null;
  overlayVisible: boolean;
  overlayOpacity: number;
  activeTool: EditingTool;
  setSelectedCaseId: (id: string | null) => void;
  setSelectedModality: (modality: Modality) => void;
  loadSegmentation: (id: string | null) => void;
  loadRevision: (id: string | null) => void;
  markDirty: () => void;
  markRevisionSaved: (id: string) => void;
  setActiveJobId: (id: string | null) => void;
  setOverlayVisible: (visible: boolean) => void;
  setOverlayOpacity: (opacity: number) => void;
  setActiveTool: (tool: EditingTool) => void;
};

const createWorkspaceState: StateCreator<WorkspaceState> = (set, get) => ({
  selectedCaseId: null,
  selectedModality: 'DWI',
  loadedSegmentationId: null,
  loadedRevisionId: null,
  baseRevisionId: null,
  dirty: false,
  activeJobId: null,
  overlayVisible: true,
  overlayOpacity: 0.55,
  activeTool: 'windowLevel',
  setSelectedCaseId: (selectedCaseId) => {
    if (get().selectedCaseId === selectedCaseId) return;
    set({
      selectedCaseId,
      selectedModality: 'DWI',
      loadedSegmentationId: null,
      loadedRevisionId: null,
      baseRevisionId: null,
      dirty: false,
      activeJobId: null,
    });
  },
  setSelectedModality: (selectedModality) => set({ selectedModality }),
  loadSegmentation: (loadedSegmentationId) => set({
    loadedSegmentationId,
    loadedRevisionId: null,
    baseRevisionId: null,
    dirty: false,
  }),
  loadRevision: (loadedRevisionId) => set({
    loadedRevisionId,
    baseRevisionId: loadedRevisionId,
    dirty: false,
  }),
  markDirty: () => set({ dirty: true }),
  markRevisionSaved: (revisionId) => set({
    loadedRevisionId: revisionId,
    baseRevisionId: revisionId,
    dirty: false,
  }),
  setActiveJobId: (activeJobId) => set({ activeJobId }),
  setOverlayVisible: (overlayVisible) => set({ overlayVisible }),
  setOverlayOpacity: (overlayOpacity) => set({ overlayOpacity }),
  setActiveTool: (activeTool) => set({ activeTool }),
});

export function createWorkspaceStore() {
  return createStore<WorkspaceState>(createWorkspaceState);
}

export const useWorkspace = create<WorkspaceState>(createWorkspaceState);
