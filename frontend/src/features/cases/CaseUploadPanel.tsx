import { useState, type ChangeEvent } from 'react';
import { api, ApiError } from '../../api/client';
import type { CaseSummary } from '../../types/api';

type Props = {
  selectedCase: CaseSummary | null;
  onCaseChanged: (item: CaseSummary) => void;
  onCaseCreated: (item: CaseSummary) => void;
};

export function CaseUploadPanel({ selectedCase, onCaseChanged, onCaseCreated }: Props) {
  const [name, setName] = useState('');
  const [dwi, setDwi] = useState<File | null>(null);
  const [adc, setAdc] = useState<File | null>(null);
  const [flair, setFlair] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    if (!name.trim() || !dwi || !adc || !flair) return;
    setBusy(true); setError(null);
    try {
      const created = await api.createCase({ name: name.trim(), dwi, adc, flair });
      onCaseCreated(created);
      setName(''); setDwi(null); setAdc(null); setFlair(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create case.');
    } finally { setBusy(false); }
  }

  void selectedCase;
  void onCaseChanged;
  const canCreate = Boolean(name.trim() && dwi && adc && flair && !busy);
  const files: Array<{ label: string; file: File | null; setFile: (file: File | null) => void }> = [
    { label: 'DWI', file: dwi, setFile: setDwi },
    { label: 'ADC', file: adc, setFile: setAdc },
    { label: 'FLAIR', file: flair, setFile: setFlair },
  ];

  return (
    <section className="panel upload-panel">
      <div className="panel-heading"><div><p className="eyebrow">Data</p><h2>Import NIfTI</h2></div></div>
      <div className="create-row">
        <input aria-label="Case name" value={name} onChange={(event: ChangeEvent<HTMLInputElement>) => setName(event.target.value)} placeholder="Case name" />
        <button type="button" className="secondary-button" disabled={!canCreate} onClick={() => void create()}>{busy ? 'Creating…' : 'Create Case'}</button>
      </div>
      {files.map(({ label, file, setFile }) => {
        return (
          <label className={`file-drop ${file ? 'complete' : ''}`} key={label}>
            <span><strong>{label} NIfTI</strong><small>{file ? file.name : '.nii or .nii.gz'}</small></span>
            <input
              type="file"
              accept=".nii,.nii.gz"
              disabled={busy}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                setFile(event.target.files?.[0] ?? null);
              }}
            />
            <span className="file-action">{file ? '✓' : 'Choose'}</span>
          </label>
        );
      })}
      <p className="muted">ADC and FLAIR stay in their native geometry; a valid mismatch is informational.</p>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
    </section>
  );
}
