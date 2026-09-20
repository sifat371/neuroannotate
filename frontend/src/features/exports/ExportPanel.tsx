import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { ExportArtifact, Revision } from '../../types/api';

type Props = {
  caseId: string | null;
  revision: Pick<Revision, 'id'> | null;
  dirty: boolean;
  pending?: boolean;
};

export function ExportPanel({ caseId, revision, dirty, pending = false }: Props) {
  const [artifact, setArtifact] = useState<ExportArtifact | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef(0);
  const identity = `${caseId ?? ''}:${revision?.id ?? ''}`;
  const identityRef = useRef(identity);
  identityRef.current = identity;

  useEffect(() => {
    requestRef.current += 1;
    setArtifact(null);
    setBusy(false);
    setError(null);
  }, [identity]);

  async function create() {
    if (!caseId || !revision || dirty || pending) return;
    const originatingCaseId = caseId;
    const originatingRevisionId = revision.id;
    const originatingIdentity = identity;
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    setBusy(true);
    setError(null);
    try {
      const result = await api.createExport(originatingCaseId, originatingRevisionId);
      if (requestRef.current === requestId && identityRef.current === originatingIdentity) {
        setArtifact(result);
      }
    } catch (err) {
      if (requestRef.current === requestId && identityRef.current === originatingIdentity) {
        setError(err instanceof ApiError ? err.message : 'Could not create export.');
      }
    } finally {
      if (requestRef.current === requestId && identityRef.current === originatingIdentity) {
        setBusy(false);
      }
    }
  }

  return (
    <section className="panel export-panel">
      <div className="panel-heading"><div><p className="eyebrow">Output</p><h2>Export</h2></div></div>
      <p className="muted">DWI native annotation space</p>
      {revision ? <p className="muted">Saved revision: {revision.id}</p> : <p className="empty-state">Save a revision before creating an export.</p>}
      {dirty ? <p className="empty-state">Save your annotation changes before creating an export.</p> : null}
      {pending ? <p className="empty-state">Wait for the revision load to finish before exporting.</p> : null}
      <button type="button" className="primary-button full" disabled={!caseId || !revision || dirty || pending || busy} onClick={() => void create()}>{busy ? 'Creating…' : 'Create Export'}</button>
      {artifact ? <div className="export-result"><p>Mask SHA-256: <code>{artifact.mask_sha256}</code></p><a href={api.exportBundleUrl(artifact.id)}>Download bundle</a><a href={api.exportMaskUrl(artifact.id)}>Download mask</a><a href={api.exportProvenanceUrl(artifact.id)}>Download provenance</a></div> : null}
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
    </section>
  );
}
