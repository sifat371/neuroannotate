import { useEffect, useState, type ChangeEvent } from 'react';
import { api, ApiError } from '../../api/client';
import type { EditableSegmentation } from '../../cornerstone/segmentation';
import type { Revision } from '../../types/api';

type Props = {
  caseId: string | null;
  sourceInferenceId: string | null;
  segmentation: EditableSegmentation | null;
  selectedRevisionId: string | null;
  dirty: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onSelectedRevisionId: (id: string | null) => void;
  onLoadRevision: (url: string) => void;
};

export function RevisionPanel({ caseId, sourceInferenceId, segmentation, selectedRevisionId, dirty, onDirtyChange, onSelectedRevisionId, onLoadRevision }: Props) {
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    if (!caseId) { setRevisions([]); return; }
    try { setRevisions(await api.listRevisions(caseId)); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Could not load revisions.'); }
  }
  useEffect(() => { void refresh(); }, [caseId]);

  async function save() {
    if (!caseId || !sourceInferenceId || !segmentation) return;
    setBusy(true); setError(null);
    try {
      const data = segmentation.getCurrentLabelmap();
      const revision = selectedRevisionId
        ? await api.saveRevision(caseId, { data, parentRevisionId: selectedRevisionId, note })
        : await api.saveRevision(caseId, { data, sourceInferenceId, note });
      segmentation.markSaved(); onDirtyChange(false); setNote(''); onSelectedRevisionId(revision.id); await refresh();
    } catch (err) { setError(err instanceof ApiError ? err.message : 'Could not save revision.'); }
    finally { setBusy(false); }
  }

  function load(revision: Revision) {
    if (!caseId) return;
    if (dirty && !window.confirm('Unsaved mask edits will be discarded.')) return;
    onSelectedRevisionId(revision.id);
    onLoadRevision(api.revisionFileUrl(revision.id));
  }

  const selected = revisions.find((revision) => revision.id === selectedRevisionId) ?? null;
  return (
    <section className="panel revision-panel">
      <div className="panel-heading"><div><p className="eyebrow">History</p><h2>Revisions</h2></div><span className="count-pill">{revisions.length}</span></div>
      <textarea aria-label="Revision note" value={note} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setNote(event.target.value)} placeholder="Optional note about your correction" rows={2} />
      <button type="button" className="secondary-button full" disabled={!segmentation || !sourceInferenceId || busy} onClick={save}>{busy ? 'Saving…' : 'Save Revision'}</button>
      <div className="revision-list">
        {sourceInferenceId ? <div className="revision-root">AI segmentation</div> : null}
        {revisions.map((revision, index) => (
          <button key={revision.id} type="button" onClick={() => load(revision)} className={`revision-item ${selectedRevisionId === revision.id ? 'selected' : ''}`}>
            <span>Revision {revisions.length - index}</span>
            <small>{new Date(revision.created_at).toLocaleString()}</small>
            {revision.note ? <small>{revision.note}</small> : null}
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
