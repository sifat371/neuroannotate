import { useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { ExportArtifact, Revision } from '../../types/api';

type Props = { caseId: string | null; revision: Pick<Revision, 'id'> | null; dirty: boolean };

export function ExportPanel({ caseId, revision, dirty }: Props) {
  const [artifact, setArtifact] = useState<ExportArtifact | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    if (!caseId || !revision || dirty) return;
    setBusy(true); setError(null);
    try { setArtifact(await api.createExport(caseId, revision.id)); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Could not create export.'); }
    finally { setBusy(false); }
  }

  return (
    <section className="panel export-panel">
      <div className="panel-heading"><div><p className="eyebrow">Output</p><h2>Export</h2></div></div>
      <p className="muted">DWI native annotation space</p>
      {revision ? <p className="muted">Saved revision: {revision.id}</p> : <p className="empty-state">Save a revision before creating an export.</p>}
      {dirty ? <p className="empty-state">Save your annotation changes before creating an export.</p> : null}
      <button type="button" className="primary-button full" disabled={!caseId || !revision || dirty || busy} onClick={() => void create()}>{busy ? 'Creating…' : 'Create Export'}</button>
      {artifact ? <div className="export-result"><p>Mask SHA-256: <code>{artifact.mask_sha256}</code></p><a href={api.exportBundleUrl(artifact.id)}>Download bundle</a><a href={api.exportMaskUrl(artifact.id)}>Download mask</a><a href={api.exportProvenanceUrl(artifact.id)}>Download provenance</a></div> : null}
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
    </section>
  );
}
