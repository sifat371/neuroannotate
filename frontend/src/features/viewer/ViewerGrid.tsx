import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/client';
import { attachLabelmap, canDisplaySegmentationOn, setOverlayOpacity, setOverlayVisible, type EditableSegmentation, type VolumeGeometry } from '../../cornerstone/segmentation';
import { createViewerSession, type ViewerSession } from '../../cornerstone/viewer';
import type { CaseDetail, CaseSummary, Modality } from '../../types/api';
import { Viewport } from './Viewport';

type Props = {
  selectedCase: CaseSummary | null;
  modality: Modality;
  inference: { sourceInferenceId: string; segmentationId: string } | null;
  revisionUrl?: string | null;
  overlayVisible: boolean;
  overlayOpacity: number;
  activeTool: 'brush' | 'erase' | 'pan' | 'zoom' | 'windowLevel';
  onSegmentationChanged: (segmentation: EditableSegmentation | null) => void;
  onEditStateChange?: (dirty: boolean, editCount: number) => void;
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

export function ViewerGrid({ selectedCase, modality, inference, revisionUrl, overlayVisible, overlayOpacity, activeTool, onSegmentationChanged, onEditStateChange }: Props) {
  const axial = useRef<HTMLDivElement | null>(null);
  const sagittal = useRef<HTMLDivElement | null>(null);
  const coronal = useRef<HTMLDivElement | null>(null);
  const sessionRef = useRef<ViewerSession | null>(null);
  const segmentationRef = useRef<EditableSegmentation | null>(null);
  const revisionRequest = useRef(0);
  const [status, setStatus] = useState('Select a case with an uploaded volume.');
  const [sessionVersion, setSessionVersion] = useState(0);
  const [editableSegmentation, setEditableSegmentation] = useState<EditableSegmentation | null>(null);
  const hasVolume = selectedCase?.modalities.includes(modality) ?? false;
  const modalityUrl = useMemo(() => selectedCase && hasVolume ? api.sourceFileUrl(selectedCase.id, modality) : null, [selectedCase, modality, hasVolume]);

  useEffect(() => {
    let cancelled = false;
    async function mount() {
      segmentationRef.current?.destroy(); segmentationRef.current = null; setEditableSegmentation(null); revisionRequest.current += 1; onSegmentationChanged(null);
      sessionRef.current?.destroy(); sessionRef.current = null;
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
      segmentationRef.current?.destroy(); segmentationRef.current = null;
      sessionRef.current?.destroy(); sessionRef.current = null;
    };
  }, [selectedCase?.id, modalityUrl, modality]);

  useEffect(() => {
    let cancelled = false;
    async function mountSegmentation() {
      if (!inference || !selectedCase || !sessionRef.current) return;
      const session = sessionRef.current;
      const blockOverlay = () => {
        segmentationRef.current?.destroy();
        segmentationRef.current = null;
        setEditableSegmentation(null);
        revisionRequest.current += 1;
        onSegmentationChanged(null);
        setStatus('Segmentation overlay unavailable in this geometry.');
      };
      const detail = await api.getCase(selectedCase.id).catch(() => null);
      if (cancelled || sessionRef.current !== session) return;
      if (!detail || detail.id !== selectedCase.id || !canAttachInSourceGeometry(detail, modality)) {
        blockOverlay();
        return;
      }
      segmentationRef.current?.destroy();
      const seg = await attachLabelmap(session, api.segmentationFileUrl(inference.segmentationId), inference.sourceInferenceId, onEditStateChange);
      if (cancelled) { seg.destroy(); return; }
      segmentationRef.current = seg;
      setEditableSegmentation(seg);
      setOverlayVisible(seg, overlayVisible);
      setOverlayOpacity(seg, overlayOpacity);
      seg.setEditingTool(activeTool);
      onSegmentationChanged(seg);
    }
    void mountSegmentation().catch((error) => setStatus(error instanceof Error ? error.message : 'Could not load segmentation.'));
    return () => { cancelled = true; };
  }, [inference?.segmentationId, inference?.sourceInferenceId, selectedCase?.id, modality, sessionVersion]);

  useEffect(() => {
    const seg = segmentationRef.current;
    if (!seg) return;
    setOverlayVisible(seg, overlayVisible);
  }, [overlayVisible]);

  useEffect(() => {
    const seg = segmentationRef.current;
    if (!seg) return;
    setOverlayOpacity(seg, overlayOpacity);
  }, [overlayOpacity]);

  useEffect(() => { segmentationRef.current?.setEditingTool(activeTool); }, [activeTool]);

  useEffect(() => {
    const requestId = revisionRequest.current + 1;
    revisionRequest.current = requestId;
    if (!revisionUrl || !editableSegmentation) return;
    void editableSegmentation.replaceFromNifti(
      revisionUrl,
      () => revisionRequest.current === requestId && segmentationRef.current === editableSegmentation,
    ).catch((error) => setStatus(error instanceof Error ? error.message : 'Could not load revision.'));
    return () => { if (revisionRequest.current === requestId) revisionRequest.current += 1; };
  }, [revisionUrl, editableSegmentation]);

  return (
    <section className="viewer-panel">
      <div className="viewer-header">
        <div><p className="eyebrow">MRI viewer</p><h2>{selectedCase?.name ?? 'No case selected'}</h2></div>
        <div className="viewer-meta"><span>{modality}</span><span>{selectedCase?.ready_for_inference ? '3 modalities aligned' : 'Import required'}</span></div>
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
