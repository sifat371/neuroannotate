import { useState, type ChangeEvent } from 'react';
import { api, ApiError } from '../../api/client';
import type { CaseSummary } from '../../types/api';

type Props = {
  selectedCase: CaseSummary | null;
  onCaseChanged: (item: CaseSummary) => void;
  onCaseCreated: (item: CaseSummary) => void;
};

type ImportMode = 'dicom' | 'nifti';

export function CaseUploadPanel({ selectedCase, onCaseChanged, onCaseCreated }: Props) {
  const [mode, setMode] = useState<ImportMode>('dicom');
  const [name, setName] = useState('');
  const [study, setStudy] = useState<File | null>(null);
  const [dwi, setDwi] = useState<File | null>(null);
  const [adc, setAdc] = useState<File | null>(null);
  const [flair, setFlair] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = mode === 'dicom'
        ? study
          ? await api.createDicomCase({ name: name.trim(), study })
          : null
        : dwi && adc && flair
          ? await api.createCase({ name: name.trim(), dwi, adc, flair })
          : null;
      if (!created) return;
      onCaseCreated(created);
      setName('');
      setStudy(null);
      setDwi(null);
      setAdc(null);
      setFlair(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create case.');
    } finally {
      setBusy(false);
    }
  }

  void selectedCase;
  void onCaseChanged;
  const canCreate = Boolean(
    name.trim()
    && !busy
    && (mode === 'dicom' ? study : dwi && adc && flair),
  );
  const files: Array<{ label: string; file: File | null; setFile: (file: File | null) => void }> = [
    { label: 'DWI', file: dwi, setFile: setDwi },
    { label: 'ADC', file: adc, setFile: setAdc },
    { label: 'FLAIR', file: flair, setFile: setFlair },
  ];

  return (
    <section className="panel upload-panel">
      <div className="panel-heading">
        <div><p className="eyebrow">Data</p><h2>Import MRI</h2></div>
      </div>
      <div className="modality-tabs" role="group" aria-label="Import format">
        <button type="button" className={mode === 'dicom' ? 'active' : ''} disabled={busy} onClick={() => setMode('dicom')}>Hospital DICOM ZIP</button>
        <button type="button" className={mode === 'nifti' ? 'active' : ''} disabled={busy} onClick={() => setMode('nifti')}>NIfTI triad</button>
      </div>
      <div className="create-row">
        <input aria-label="Case name" value={name} onChange={(event: ChangeEvent<HTMLInputElement>) => setName(event.target.value)} placeholder="Research case ID" />
        <button type="button" className="secondary-button" disabled={!canCreate} onClick={() => void create()}>{busy ? 'Importing…' : 'Import Case'}</button>
      </div>

      {mode === 'dicom' ? (
        <>
          <label className={`file-drop ${study ? 'complete' : ''}`}>
            <span><strong>DICOM study ZIP</strong><small>{study ? study.name : 'Scanner/CD export as .zip'}</small></span>
            <input
              aria-label="DICOM study ZIP"
              type="file"
              accept=".zip,application/zip"
              disabled={busy}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setStudy(event.target.files?.[0] ?? null)}
            />
            <span className="file-action">{study ? '✓' : 'Choose'}</span>
          </label>
          <p className="muted">
            NeuroAnnotate auto-detects DWI, ADC and FLAIR, converts them locally, and does not retain the uploaded raw DICOM study after import.
          </p>
        </>
      ) : (
        <>
          {files.map(({ label, file, setFile }) => (
            <label className={`file-drop ${file ? 'complete' : ''}`} key={label}>
              <span><strong>{label} NIfTI</strong><small>{file ? file.name : '.nii or .nii.gz'}</small></span>
              <input
                aria-label={`${label} NIfTI`}
                type="file"
                accept=".nii,.nii.gz"
                disabled={busy}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)}
              />
              <span className="file-action">{file ? '✓' : 'Choose'}</span>
            </label>
          ))}
          <p className="muted">ADC and FLAIR stay in their native geometry; a valid mismatch is informational.</p>
        </>
      )}
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
    </section>
  );
}
