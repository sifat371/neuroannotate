import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { api, ApiError } from '../../api/client';
import type { EditableSegmentation } from '../../cornerstone/segmentation';
import { toNiftiVoxelOrder } from '../../cornerstone/serializeLabelmap';
import type { Revision } from '../../types/api';

type Props = {
  caseId: string | null;
  sourceInferenceId: string | null;
  segmentation: EditableSegmentation | null;
  selectedRevisionId: string | null;
  dirty: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onRevisionSaved: (revision: Revision, clean: boolean) => void;
  onRevisionLoaded: (revision: Revision) => void;
  onLoadPendingChange?: (pending: boolean) => void;
};

type Context = Pick<Props, 'caseId' | 'sourceInferenceId' | 'segmentation' | 'selectedRevisionId'>;

export function RevisionPanel({
  caseId,
  sourceInferenceId,
  segmentation,
  selectedRevisionId,
  dirty,
  onDirtyChange,
  onRevisionSaved,
  onRevisionLoaded,
  onLoadPendingChange,
}: Props) {
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [loadBusy, setLoadBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRequest = useRef(0);
  const saveRequest = useRef(0);
  const loadRequest = useRef(0);
  const contextRef = useRef<Context>({ caseId, sourceInferenceId, segmentation, selectedRevisionId });
  contextRef.current = { caseId, sourceInferenceId, segmentation, selectedRevisionId };

  async function refresh(expectedCaseId: string | null = contextRef.current.caseId) {
    const requestId = listRequest.current + 1;
    listRequest.current = requestId;
    if (!expectedCaseId) {
      setRevisions([]);
      return;
    }
    try {
      const next = await api.listRevisions(expectedCaseId);
      if (listRequest.current === requestId && contextRef.current.caseId === expectedCaseId) {
        setRevisions(next);
      }
    } catch (err) {
      if (listRequest.current === requestId && contextRef.current.caseId === expectedCaseId) {
        setError(err instanceof ApiError ? err.message : 'Could not load revisions.');
      }
    }
  }

  useEffect(() => {
    listRequest.current += 1;
    saveRequest.current += 1;
    loadRequest.current += 1;
    setBusy(false);
    setLoadBusy(false);
    setError(null);
    onLoadPendingChange?.(false);
    void refresh(caseId);
  }, [caseId]);

  async function save() {
    if (!caseId || !sourceInferenceId || !segmentation || loadBusy) return;
    const originatingCaseId = caseId;
    const originatingInferenceId = sourceInferenceId;
    const originatingSegmentation = segmentation;
    const originatingBaseRevisionId = selectedRevisionId;
    const snapshotEditCount = segmentation.editCount;
    const data = toNiftiVoxelOrder(segmentation.getCurrentLabelmap());
    const requestId = saveRequest.current + 1;
    saveRequest.current = requestId;
    setBusy(true);
    setError(null);
    try {
      const revision = originatingBaseRevisionId
        ? await api.saveRevision(originatingCaseId, { data, parentRevisionId: originatingBaseRevisionId, note })
        : await api.saveRevision(originatingCaseId, { data, sourceInferenceId: originatingInferenceId, note });
      const current = contextRef.current;
      const stillSameContext = saveRequest.current === requestId
        && current.caseId === originatingCaseId
        && current.sourceInferenceId === originatingInferenceId
        && current.segmentation === originatingSegmentation
        && current.selectedRevisionId === originatingBaseRevisionId;
      if (!stillSameContext) return;

      const clean = originatingSegmentation.markSaved(snapshotEditCount);
      onDirtyChange(!clean);
      onRevisionSaved(revision, clean);
      setNote('');
      await refresh(originatingCaseId);
    } catch (err) {
      if (saveRequest.current === requestId && contextRef.current.caseId === originatingCaseId) {
        setError(err instanceof ApiError ? err.message : 'Could not save revision.');
      }
    } finally {
      if (saveRequest.current === requestId) setBusy(false);
    }
  }

  async function load(revision: Revision) {
    if (!caseId || !segmentation || busy || loadBusy) return;
    if (dirty && !window.confirm('Unsaved mask edits will be discarded.')) return;
    const originatingCaseId = caseId;
    const originatingSegmentation = segmentation;
    const requestId = loadRequest.current + 1;
    loadRequest.current = requestId;
    setLoadBusy(true);
    setError(null);
    onLoadPendingChange?.(true);
    try {
      const applied = await originatingSegmentation.replaceFromNifti(
        api.revisionFileUrl(revision.id),
        () => loadRequest.current === requestId
          && contextRef.current.caseId === originatingCaseId
          && contextRef.current.segmentation === originatingSegmentation,
      );
      if (!applied) return;
      if (
        loadRequest.current !== requestId
        || contextRef.current.caseId !== originatingCaseId
        || contextRef.current.segmentation !== originatingSegmentation
      ) return;
      onDirtyChange(false);
      onRevisionLoaded(revision);
    } catch (err) {
      if (loadRequest.current === requestId && contextRef.current.caseId === originatingCaseId) {
        setError(err instanceof ApiError ? err.message : 'Could not load revision.');
      }
    } finally {
      if (loadRequest.current === requestId) {
        setLoadBusy(false);
        onLoadPendingChange?.(false);
      }
    }
  }

  const selected = revisions.find((revision) => revision.id === selectedRevisionId) ?? null;
  return (
    <section className="panel revision-panel">
      <div className="panel-heading"><div><p className="eyebrow">History</p><h2>Revisions</h2></div><span className="count-pill">{revisions.length}</span></div>
      <textarea aria-label="Revision note" value={note} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setNote(event.target.value)} placeholder="Optional note about your correction" rows={2} />
      <button type="button" className="secondary-button full" disabled={!segmentation || !sourceInferenceId || busy || loadBusy} onClick={() => void save()}>{busy ? 'Saving…' : 'Save Revision'}</button>
      {loadBusy ? <p className="muted">Loading revision…</p> : null}
      <div className="revision-list">
        {sourceInferenceId ? <div className="revision-root">AI segmentation</div> : null}
        {revisions.map((revision, index) => (
          <button key={revision.id} type="button" disabled={!segmentation || busy || loadBusy} onClick={() => void load(revision)} className={`revision-item ${selectedRevisionId === revision.id ? 'selected' : ''}`}>
            <span>Revision {revisions.length - index}</span>
            <small>{new Date(revision.created_at).toLocaleString()}</small>
            {revision.note ? <small>{revision.note}</small> : null}
            <small>Lesion volume: {Number(revision.edit_stats.lesion_volume_ml ?? 0).toFixed(2)} mL</small>
            <small>Added {revision.edit_stats.added_voxels ?? 0} · Removed {revision.edit_stats.removed_voxels ?? 0}</small>
            <small>Base: {revision.parent_revision_id ? `Revision ${revision.parent_revision_id}` : 'AI segmentation'}</small>
          </button>
        ))}
        {sourceInferenceId && revisions.length === 0 ? <p className="empty-state">No saved revisions yet. The AI segmentation is ready to annotate.</p> : null}
      </div>
      {selected ? <p className="muted">Editing base: {selected.parent_revision_id ? `Revision ${selected.parent_revision_id}` : 'AI segmentation'}</p> : null}
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
    </section>
  );
}
