import { useState, type ChangeEvent } from 'react';
import { api, ApiError } from '../../api/client';
import type { CaseSummary, Modality } from '../../types/api';

const MODALITIES: Modality[] = ['DWI', 'ADC', 'FLAIR'];

type Props = {
  selectedCase: CaseSummary | null;
  onCaseChanged: (item: CaseSummary) => void;
  onCaseCreated: (item: CaseSummary) => void;
};

export function CaseUploadPanel({ selectedCase, onCaseChanged, onCaseCreated }: Props) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload(modality: Modality, file: File) {
    if (!selectedCase) return;
    setBusy(modality); setError(null);
    try {
      onCaseChanged(await api.uploadModality(selectedCase.id, modality, file));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed.');
    } finally { setBusy(null); }
  }

  return (
    <section className="panel upload-panel">
      <div className="panel-heading"><div><p className="eyebrow">Data</p><h2>Import NIfTI</h2></div></div>
      <div className="create-row">
        <input aria-label="New case name" value={name} onChange={(event: ChangeEvent<HTMLInputElement>) => setName(event.target.value)} placeholder="New case name" />
        <button type="button" className="secondary-button" disabled>Import all three files together</button>
      </div>
      {MODALITIES.map((modality) => {
        const present = selectedCase?.modalities.includes(modality) ?? false;
        return (
          <label className={`file-drop ${present ? 'complete' : ''}`} key={modality}>
            <span><strong>{modality} NIfTI</strong><small>{present ? 'Uploaded' : '.nii or .nii.gz'}</small></span>
            <input
              type="file"
              accept=".nii,.nii.gz"
              disabled={!selectedCase || present || busy === modality}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                const file = event.target.files?.[0];
                if (file) void upload(modality, file);
                event.currentTarget.value = '';
              }}
            />
            <span className="file-action">{busy === modality ? 'Uploading…' : present ? '✓' : 'Choose'}</span>
          </label>
        );
      })}
      {!selectedCase ? <p className="muted">Select a case before uploading volumes.</p> : null}
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
    </section>
  );
}
