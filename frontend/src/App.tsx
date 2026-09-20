import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { api, ApiError } from './api/client';
import type { EditableSegmentation } from './cornerstone/segmentation';
import { AnnotationToolbar } from './features/annotation/AnnotationToolbar';
import { CaseSidebar } from './features/cases/CaseSidebar';
import { CaseUploadPanel } from './features/cases/CaseUploadPanel';
import { InferenceControls } from './features/inference/InferenceControls';
import { RevisionPanel } from './features/revisions/RevisionPanel';
import { ViewerGrid } from './features/viewer/ViewerGrid';
import { ExportPanel } from './features/exports/ExportPanel';
import { SystemStatus } from './features/system/SystemStatus';
import { useWorkspace } from './state/workspace';
import type { CaseSummary, InferenceJob, Modality, Revision, SystemHealth } from './types/api';

const modalities: Modality[] = ['DWI', 'ADC', 'FLAIR'];
const HEALTH_POLL_MS = 5000;

export default function App() {
  const workspace = useWorkspace();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inference, setInference] = useState<{ sourceInferenceId: string; segmentationId: string } | null>(null);
  const [activeJob, setActiveJob] = useState<InferenceJob | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [segmentation, setSegmentation] = useState<EditableSegmentation | null>(null);
  const [baseMaskUrl, setBaseMaskUrl] = useState<string | null>(null);
  const [revisionLoadPending, setRevisionLoadPending] = useState(false);
  const [unsavedEditCount, setUnsavedEditCount] = useState(0);
  const selectedCaseIdRef = useRef<string | null>(workspace.selectedCaseId);
  selectedCaseIdRef.current = workspace.selectedCaseId;
  const selectedCase = useMemo(() => cases.find((item) => item.id === workspace.selectedCaseId) ?? null, [cases, workspace.selectedCaseId]);

  useEffect(() => {
    api.listCases().then((items) => {
      setCases(items);
      if (!workspace.selectedCaseId && items.length) workspace.setSelectedCaseId(items[0].id);
    }).catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load cases.')).finally(() => setLoadingCases(false));
  }, []);

  useEffect(() => {
    let live = true;
    const refresh = () => {
      void api.getSystemHealth().then((next) => {
        if (live) setHealth(next);
      }).catch(() => {
        if (live) setHealth(null);
      });
    };
    refresh();
    const interval = window.setInterval(refresh, HEALTH_POLL_MS);
    return () => { live = false; window.clearInterval(interval); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setInference(null);
    setActiveJob(null);
    setSegmentation(null);
    setBaseMaskUrl(null);
    setRevisionLoadPending(false);
    setUnsavedEditCount(0);
    if (!selectedCase) return;
    const caseId = selectedCase.id;
    void api.listInferenceJobs(caseId).then((jobs) => {
      if (cancelled || selectedCaseIdRef.current !== caseId) return;
      // API order is newest-first. Keep the latest attempt visible even if it
      // failed, while independently restoring the newest usable segmentation.
      const latestAttempt = jobs[0] ?? null;
      const latestCompleted = jobs.find((job) => job.status === 'completed' && job.segmentation_id) ?? null;
      if (latestAttempt) {
        setActiveJob(latestAttempt);
        workspace.setActiveJobId(latestAttempt.id);
      }
      if (latestCompleted?.segmentation_id) {
        setInference({ sourceInferenceId: latestCompleted.id, segmentationId: latestCompleted.segmentation_id });
        workspace.loadSegmentation(latestCompleted.segmentation_id);
        setBaseMaskUrl(api.segmentationFileUrl(latestCompleted.segmentation_id));
      }
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [selectedCase?.id]);

  function handleJobChange(job: InferenceJob, expectedCaseId = selectedCaseIdRef.current) {
    if (job.case_id !== expectedCaseId || job.case_id !== selectedCaseIdRef.current) return;
    setActiveJob(job);
    workspace.setActiveJobId(job.id);
  }

  function loadCompletedJob(job: InferenceJob) {
    if (job.case_id !== selectedCaseIdRef.current || job.status !== 'completed' || !job.segmentation_id) return;
    if (job.segmentation_id !== workspace.loadedSegmentationId && workspace.dirty && !window.confirm('Unsaved mask edits will be discarded. Load the new AI segmentation?')) return;
    setSegmentation(null);
    setInference({ sourceInferenceId: job.id, segmentationId: job.segmentation_id });
    workspace.loadSegmentation(job.segmentation_id);
    setBaseMaskUrl(api.segmentationFileUrl(job.segmentation_id));
    setRevisionLoadPending(false);
    setUnsavedEditCount(0);
  }

  function upsertCase(item: CaseSummary) {
    setCases((existing) => {
      const found = existing.some((candidate) => candidate.id === item.id);
      return found ? existing.map((candidate) => candidate.id === item.id ? item : candidate) : [item, ...existing];
    });
  }

  function selectCase(id: string) {
    if (id !== workspace.selectedCaseId && workspace.dirty && !window.confirm('Unsaved mask edits will be discarded.')) return;
    workspace.setSelectedCaseId(id);
  }

  function selectCreatedCase(item: CaseSummary) {
    upsertCase(item);
    if (workspace.dirty && workspace.selectedCaseId && !window.confirm('Unsaved mask edits will be discarded.')) return;
    workspace.setSelectedCaseId(item.id);
  }

  function setDirtyState(dirty: boolean) {
    workspace.setDirty(dirty);
    if (!dirty) setUnsavedEditCount(0);
  }

  function updateEditState(dirty: boolean, count: number) {
    workspace.setDirty(dirty);
    setUnsavedEditCount(count);
  }

  function revisionSaved(revision: Revision, clean: boolean) {
    workspace.markRevisionSaved(revision.id, clean);
    setBaseMaskUrl(api.revisionFileUrl(revision.id));
  }

  function revisionLoaded(revision: Revision) {
    workspace.loadRevision(revision.id);
    setBaseMaskUrl(api.revisionFileUrl(revision.id));
    setUnsavedEditCount(0);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block"><div className="brand-mark">N</div><div><h1>NeuroAnnotate</h1><p>AI-assisted brain MRI annotation workspace</p></div></div>
        <div className="research-badge">Research & portfolio software · Not for clinical use</div>
      </header>
      {error ? <div className="global-error" role="alert">{error}</div> : null}
      <main className="workspace-layout">
        <aside className="left-rail">
          <CaseSidebar cases={cases} selectedCaseId={workspace.selectedCaseId} onSelect={selectCase} loading={loadingCases} />
          <CaseUploadPanel selectedCase={selectedCase} onCaseChanged={upsertCase} onCaseCreated={selectCreatedCase} />
        </aside>
        <section className="center-stage">
          <div className="viewer-controls">
            <div className="modality-tabs" role="group" aria-label="MRI modality">
              {modalities.map((modality) => <button type="button" key={modality} className={workspace.selectedModality === modality ? 'active' : ''} disabled={!selectedCase?.modalities.includes(modality)} onClick={() => workspace.setSelectedModality(modality)}>{modality}</button>)}
            </div>
            <div className="overlay-controls">
              <label><input type="checkbox" checked={workspace.overlayVisible} disabled={!segmentation} onChange={(event: ChangeEvent<HTMLInputElement>) => workspace.setOverlayVisible(event.target.checked)} /> Overlay</label>
              <input aria-label="Overlay opacity" type="range" min="0" max="1" step="0.05" value={workspace.overlayOpacity} disabled={!segmentation} onChange={(event: ChangeEvent<HTMLInputElement>) => workspace.setOverlayOpacity(Number(event.target.value))} />
            </div>
          </div>
          <AnnotationToolbar segmentation={segmentation} activeTool={workspace.activeTool} onToolChange={workspace.setActiveTool} baseLabel={workspace.baseRevisionId ? `Revision ${workspace.baseRevisionId}` : inference ? 'AI segmentation' : 'No segmentation'} unsavedEditCount={unsavedEditCount} />
          <ViewerGrid selectedCase={selectedCase} modality={workspace.selectedModality} inference={inference} baseMaskUrl={baseMaskUrl} overlayVisible={workspace.overlayVisible} overlayOpacity={workspace.overlayOpacity} activeTool={workspace.activeTool} onSegmentationChanged={setSegmentation} onEditStateChange={updateEditState} />
        </section>
        <aside className="right-rail">
          <InferenceControls selectedCase={selectedCase} job={activeJob} onJobChange={handleJobChange} health={health} loadedSegmentationId={workspace.loadedSegmentationId} onLoadCompleted={loadCompletedJob} />
          <RevisionPanel
            caseId={selectedCase?.id ?? null}
            sourceInferenceId={inference?.sourceInferenceId ?? null}
            segmentation={segmentation}
            selectedRevisionId={workspace.loadedRevisionId}
            dirty={workspace.dirty}
            onDirtyChange={setDirtyState}
            onRevisionSaved={revisionSaved}
            onRevisionLoaded={revisionLoaded}
            onLoadPendingChange={setRevisionLoadPending}
          />
          <ExportPanel caseId={selectedCase?.id ?? null} revision={workspace.loadedRevisionId ? { id: workspace.loadedRevisionId } : null} dirty={workspace.dirty} pending={revisionLoadPending} />
          <SystemStatus health={health} />
          <section className="panel shortcut-panel"><p className="eyebrow">Shortcuts</p><div><kbd>⌘/Ctrl Z</kbd><span>Undo</span></div><div><kbd>⇧ ⌘/Ctrl Z</kbd><span>Redo</span></div><div><kbd>Wheel</kbd><span>Change slice</span></div></section>
        </aside>
      </main>
    </div>
  );
}
