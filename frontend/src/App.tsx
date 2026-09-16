import { useEffect, useMemo, useState, type ChangeEvent } from 'react';
import { api, ApiError } from './api/client';
import type { EditableSegmentation } from './cornerstone/segmentation';
import { AnnotationToolbar } from './features/annotation/AnnotationToolbar';
import { CaseSidebar } from './features/cases/CaseSidebar';
import { CaseUploadPanel } from './features/cases/CaseUploadPanel';
import { InferenceControls } from './features/inference/InferenceControls';
import { RevisionPanel } from './features/revisions/RevisionPanel';
import { ViewerGrid } from './features/viewer/ViewerGrid';
import { useWorkspace } from './state/workspace';
import type { CaseSummary, InferenceRun, Modality } from './types/api';

const modalities: Modality[] = ['DWI', 'ADC', 'FLAIR'];

export default function App() {
  const workspace = useWorkspace();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inference, setInference] = useState<InferenceRun | null>(null);
  const [segmentation, setSegmentation] = useState<EditableSegmentation | null>(null);
  const [revisionUrl, setRevisionUrl] = useState<string | null>(null);
  const selectedCase = useMemo(() => cases.find((item) => item.id === workspace.selectedCaseId) ?? null, [cases, workspace.selectedCaseId]);

  useEffect(() => {
    api.listCases().then((items) => {
      setCases(items);
      if (!workspace.selectedCaseId && items.length) workspace.setSelectedCaseId(items[0].id);
    }).catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load cases.')).finally(() => setLoadingCases(false));
  }, []);

  useEffect(() => {
    setInference(null); setSegmentation(null); setRevisionUrl(null);
    if (!selectedCase) return;
    void api.getLatestSegmentation(selectedCase.id).then(setInference).catch(() => undefined);
  }, [selectedCase?.id]);

  function upsertCase(item: CaseSummary) {
    setCases((existing) => {
      const found = existing.some((candidate) => candidate.id === item.id);
      return found ? existing.map((candidate) => candidate.id === item.id ? item : candidate) : [item, ...existing];
    });
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
          <CaseSidebar cases={cases} selectedCaseId={workspace.selectedCaseId} onSelect={workspace.setSelectedCaseId} loading={loadingCases} />
          <CaseUploadPanel selectedCase={selectedCase} onCaseChanged={upsertCase} onCaseCreated={(item) => { upsertCase(item); workspace.setSelectedCaseId(item.id); }} />
        </aside>
        <section className="center-stage">
          <div className="viewer-controls">
            <div className="modality-tabs" role="group" aria-label="MRI modality">
              {modalities.map((modality) => <button type="button" key={modality} className={workspace.activeModality === modality ? 'active' : ''} disabled={!selectedCase?.modalities.includes(modality)} onClick={() => workspace.setActiveModality(modality)}>{modality}</button>)}
            </div>
            <div className="overlay-controls">
              <label><input type="checkbox" checked={workspace.overlayVisible} disabled={!segmentation} onChange={(event: ChangeEvent<HTMLInputElement>) => workspace.setOverlayVisible(event.target.checked)} /> Overlay</label>
              <input aria-label="Overlay opacity" type="range" min="0" max="1" step="0.05" value={workspace.overlayOpacity} disabled={!segmentation} onChange={(event: ChangeEvent<HTMLInputElement>) => workspace.setOverlayOpacity(Number(event.target.value))} />
            </div>
          </div>
          <AnnotationToolbar segmentation={segmentation} activeTool={workspace.activeTool} onToolChange={workspace.setActiveTool} />
          <ViewerGrid selectedCase={selectedCase} modality={workspace.activeModality} inference={inference} revisionUrl={revisionUrl} overlayVisible={workspace.overlayVisible} overlayOpacity={workspace.overlayOpacity} activeTool={workspace.activeTool} onSegmentationChanged={setSegmentation} />
        </section>
        <aside className="right-rail">
          <InferenceControls selectedCase={selectedCase} onSegmentationReady={(run) => { setInference(run); workspace.setSelectedRevisionId(null); setRevisionUrl(null); }} />
          <RevisionPanel caseId={selectedCase?.id ?? null} sourceInferenceId={inference?.id ?? null} segmentation={segmentation} selectedRevisionId={workspace.selectedRevisionId} onSelectedRevisionId={workspace.setSelectedRevisionId} onLoadRevision={setRevisionUrl} />
          <section className="panel shortcut-panel"><p className="eyebrow">Shortcuts</p><div><kbd>⌘/Ctrl Z</kbd><span>Undo</span></div><div><kbd>⇧ ⌘/Ctrl Z</kbd><span>Redo</span></div><div><kbd>Wheel</kbd><span>Change slice</span></div></section>
        </aside>
      </main>
    </div>
  );
}
