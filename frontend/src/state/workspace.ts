import { create } from 'zustand';
import type { Modality } from '../types/api';

export type EditingTool = 'brush' | 'erase' | 'pan' | 'zoom' | 'windowLevel';

type WorkspaceState = {
  selectedCaseId: string | null;
  activeModality: Modality;
  overlayVisible: boolean;
  overlayOpacity: number;
  activeTool: EditingTool;
  selectedRevisionId: string | null;
  setSelectedCaseId: (id: string | null) => void;
  setActiveModality: (modality: Modality) => void;
  setOverlayVisible: (visible: boolean) => void;
  setOverlayOpacity: (opacity: number) => void;
  setActiveTool: (tool: EditingTool) => void;
  setSelectedRevisionId: (id: string | null) => void;
};

export const useWorkspace = create<WorkspaceState>((set) => ({
  selectedCaseId: null,
  activeModality: 'DWI',
  overlayVisible: true,
  overlayOpacity: 0.55,
  activeTool: 'windowLevel',
  selectedRevisionId: null,
  setSelectedCaseId: (selectedCaseId) => set({ selectedCaseId, selectedRevisionId: null }),
  setActiveModality: (activeModality) => set({ activeModality }),
  setOverlayVisible: (overlayVisible) => set({ overlayVisible }),
  setOverlayOpacity: (overlayOpacity) => set({ overlayOpacity }),
  setActiveTool: (activeTool) => set({ activeTool }),
  setSelectedRevisionId: (selectedRevisionId) => set({ selectedRevisionId }),
}));
