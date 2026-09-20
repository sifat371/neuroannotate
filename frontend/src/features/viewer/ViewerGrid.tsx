import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/client';
import {
  attachLabelmap,
  canDisplaySegmentationOn,
  setOverlayOpacity,
  setOverlayVisible,
  type EditableSegmentation,
  type VolumeGeometry,
} from '../../cornerstone/segmentation';
import type { SerializedLabelmap } from '../../cornerstone/serializeLabelmap';
import { createViewerSession, type ViewerSession } from '../../cornerstone/viewer';
import type { CaseDetail, CaseSummary, Modality } from '../../types/api';
import { Viewport } from './Viewport';

type Props = {
  selectedCase: CaseSummary | null;
  modality: Modality;
  inference: { sourceInferenceId: string; segmentationId: string } | null;
  baseMaskUrl?: string | null;
  overlayVisible: boolean;
  overlayOpacity: number;
  activeTool: 'brush' | 'erase' | 'pan' | 'zoom' | 'windowLevel';
  onSegmentationChanged: (segmentation: EditableSegmentation | null) => void;
  onEditStateChange?: (dirty: boolean, editCount: number) => void;
};

type PreservedMask = {
  key: string;
  data: SerializedLabelmap;
  dirty: boolean;
  editCount: number;
};

function sourceGeometry(detail: CaseDetail, modality: Modality): VolumeGeometry | null {
  if (!Array.isArray(detail?.sources)) return null;
  const geometries = new Map<Modality, VolumeGeometry>();
  for (const source of detail.sources) {
    if (source?.modality !== 'DWI' && source?.modality !== 'ADC' && source?.modality !== 'FLAIR') return null;
    if (geometries.has(source.modality)) return null;
    geometries.set(source.modality, { shape: source.shape, affine: source.affine });
  }
  return geometries.get(modality) ?? null;
}

function canAttachInSourceGeometry(detail: CaseDetail, modality: Modality): boolean {
  const source = sourceGeometry(detail, modality);
  const dwi = sourceGeometry(detail, 'DWI');
  return source !== null && dwi !== null && canDisplaySegmentationOn(source, dwi);
}

function annotationKey(caseId: string, inference: NonNullable<Props['inference']>): string {
  return `${caseId}:${inference.sourceInferenceId}:${inference.segmentationId}`;
}

export function ViewerGrid({
  selectedCase,
  modality,
  inference,
  baseMaskUrl,
  overlayVisible,
  overlayOpacity,
  activeTool,
  onSegmentationChanged,
  onEditStateChange,
}: Props) {
  const axial = useRef<HTMLDivElement | null>(null);
  const sagittal = useRef<HTMLDivElement | null>(null);
  const coronal = useRef<HTMLDivElement | null>(null);
  const sessionRef = useRef<ViewerSession | null>(null);
  const segmentationRef = useRef<EditableSegmentation | null>(null);
  const segmentationKeyRef = useRef<string | null>(null);
  const preservedMaskRef = useRef<PreservedMask | null>(null);
  const [status, setStatus] = useState('Select a case with an uploaded volume.');
  const [sessionVersion, setSessionVersion] = useState(0);
  const hasVolume = selectedCase?.modalities.includes(modality) ?? false;
  const modalityUrl = useMemo(
    () => selectedCase && hasVolume ? api.sourceFileUrl(selectedCase.id, modality) : null,
    [selectedCase, modality, hasVolume],
  );

  function destroyEditable(preserve: boolean) {
    const current = segmentationRef.current;
    const key = segmentationKeyRef.current;
    if (current && preserve && key) {
      try {
        preservedMaskRef.current = {
          key,
          data: current.getCurrentLabelmap(),
          dirty: current.dirty,
          editCount: current.editCount,
        };
      } catch {
        // If the Cornerstone volume has already disappeared, keep the last
        // successfully preserved canonical mask rather than replacing it.
      }
    }
    if (current) current.destroy();
    segmentationRef.current = null;
    segmentationKeyRef.current = null;
    onSegmentationChanged(null);
  }

  useEffect(() => {
    let cancelled = false;
    async function mount() {
      sessionRef.current?.destroy();
      sessionRef.current = null;
      setSessionVersion((value) => value + 1);
      if (!selectedCase || !modalityUrl || !axial.current || !sagittal.current || !coronal.current) {
        setStatus(hasVolume ? 'Viewer is not ready.' : `${modality} has not been uploaded.`);
        return;
      }
      setStatus(`Loading ${modality}…`);
      try {
        const session = await createViewerSession({
          caseId: selectedCase.id,
          modality,
          modalityUrl,
          elements: { AXIAL: axial.current, SAGITTAL: sagittal.current, CORONAL: coronal.current },
        });
        if (cancelled) { session.destroy(); return; }
        sessionRef.current = session;
        setSessionVersion((value) => value + 1);
        setStatus('');
      } catch (error) {
        setStatus(error instanceof Error ? error.message : 'Could not initialize MRI viewer.');
      }
    }
    void mount();
    return () => {
      cancelled = true;
      destroyEditable(true);
      sessionRef.current?.destroy();
      sessionRef.current = null;
    };
  }, [selectedCase?.id, modalityUrl, modality]);

  useEffect(() => {
    let cancelled = false;
    async function mountSegmentation() {
      if (!inference || !selectedCase || !sessionRef.current) {
        if (!inference) {
          destroyEditable(false);
          preservedMaskRef.current = null;
        }
        return;
      }
      const session = sessionRef.current;
      const key = annotationKey(selectedCase.id, inference);
      const detail = await api.getCase(selectedCase.id).catch(() => null);
      if (cancelled || sessionRef.current !== session) return;
      if (!detail || detail.id !== selectedCase.id || !canAttachInSourceGeometry(detail, modality)) {
        destroyEditable(true);
        setStatus('Segmentation overlay unavailable in this geometry.');
        return;
      }

      // A different AI result is a different annotation lineage. Its pixels
      // must never inherit an unsaved mask from the previous lineage.
      if (segmentationRef.current && segmentationKeyRef.current !== key) {
        destroyEditable(false);
      }
      const preserved = preservedMaskRef.current?.key === key ? preservedMaskRef.current : null;
      const initialUrl = baseMaskUrl ?? api.segmentationFileUrl(inference.segmentationId);
      const seg = await attachLabelmap(session, initialUrl, inference.sourceInferenceId, onEditStateChange);
      if (cancelled || sessionRef.current !== session) { seg.destroy(); return; }
      if (preserved) {
        seg.replaceFromLabelmap(preserved.data, { dirty: preserved.dirty, editCount: preserved.editCount });
      }
      segmentationRef.current = seg;
      segmentationKeyRef.current = key;
      setOverlayVisible(seg, overlayVisible);
      setOverlayOpacity(seg, overlayOpacity);
      seg.setEditingTool(activeTool);
      onSegmentationChanged(seg);
      setStatus('');
    }
    void mountSegmentation().catch((error) => setStatus(error instanceof Error ? error.message : 'Could not load segmentation.'));
    return () => { cancelled = true; };
  }, [inference?.segmentationId, inference?.sourceInferenceId, selectedCase?.id, modality, sessionVersion]);

  useEffect(() => {
    const seg = segmentationRef.current;
    if (seg) setOverlayVisible(seg, overlayVisible);
  }, [overlayVisible]);

  useEffect(() => {
    const seg = segmentationRef.current;
    if (seg) setOverlayOpacity(seg, overlayOpacity);
  }, [overlayOpacity]);

  useEffect(() => { segmentationRef.current?.setEditingTool(activeTool); }, [activeTool]);

  return (
    <section className="viewer-panel">
      <div className="viewer-header">
        <div><p className="eyebrow">MRI viewer</p><h2>{selectedCase?.name ?? 'No case selected'}</h2></div>
        <div className="viewer-meta">
          <span>{modality}{modality === 'DWI' ? ' · Annotation reference' : ' · Native reference'}</span>
          <span>{selectedCase?.ready_for_inference ? 'DWI + ADC + FLAIR ready' : 'Import required'}</span>
        </div>
      </div>
      <div className="viewer-grid">
        <Viewport ref={axial} orientation="AXIAL" label="Axial MRI viewport" />
        <Viewport ref={sagittal} orientation="SAGITTAL" label="Sagittal MRI viewport" />
        <Viewport ref={coronal} orientation="CORONAL" label="Coronal MRI viewport" />
      </div>
      {status ? <div className="viewer-status">{status}</div> : null}
    </section>
  );
}
