import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { ExportPanel } from '../src/features/exports/ExportPanel';
import type { ExportArtifact } from '../src/types/api';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, createExport: vi.fn() } };
});

const revision = { id: 'rev-1', case_id: 'case-1', source_inference_id: 'job-1', source_segmentation_id: 'seg-1', parent_revision_id: null, sha256: 'revision-hash', edit_stats: {}, note: null, created_at: '2026-09-17T12:00:00Z' };
const artifact: ExportArtifact = { id: 'export-1', case_id: 'case-1', revision_id: 'rev-1', mask_sha256: 'mask-hash', created_at: '', mask_url: '/mask', provenance_url: '/provenance', bundle_url: '/bundle' };

function deferred<T>() {
  let resolve!: (value: T) => void;
  return { promise: new Promise<T>((done) => { resolve = done; }), resolve };
}

beforeEach(() => vi.clearAllMocks());

test('disables export while unsaved edits or a revision load exists', () => {
  const { rerender } = render(<ExportPanel caseId="case-1" revision={revision} dirty />);
  expect(screen.getByRole('button', { name: /create export/i })).toBeDisabled();
  expect(screen.getByText(/save your annotation changes/i)).toBeInTheDocument();
  rerender(<ExportPanel caseId="case-1" revision={revision} dirty={false} pending />);
  expect(screen.getByRole('button', { name: /create export/i })).toBeDisabled();
  expect(screen.getByText(/wait for the revision load/i)).toBeInTheDocument();
});

test('creates an export only from the selected saved revision and shows DWI-space output links', async () => {
  vi.mocked(api.createExport).mockResolvedValue(artifact);
  render(<ExportPanel caseId="case-1" revision={revision} dirty={false} />);
  await userEvent.click(screen.getByRole('button', { name: /create export/i }));
  await waitFor(() => expect(api.createExport).toHaveBeenCalledWith('case-1', 'rev-1'));
  expect(screen.getByText(/DWI native annotation space/i)).toBeInTheDocument();
  expect(screen.getByText('mask-hash')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /download bundle/i })).toHaveAttribute('href', expect.stringContaining('/bundle'));
});

test('clears an export artifact when case or revision identity changes', async () => {
  vi.mocked(api.createExport).mockResolvedValue(artifact);
  const { rerender } = render(<ExportPanel caseId="case-1" revision={revision} dirty={false} />);
  await userEvent.click(screen.getByRole('button', { name: /create export/i }));
  expect(await screen.findByText('mask-hash')).toBeInTheDocument();
  rerender(<ExportPanel caseId="case-1" revision={{ id: 'rev-2' }} dirty={false} />);
  expect(screen.queryByText('mask-hash')).not.toBeInTheDocument();
  rerender(<ExportPanel caseId="case-2" revision={{ id: 'rev-2' }} dirty={false} />);
  expect(screen.queryByText('mask-hash')).not.toBeInTheDocument();
});

test('ignores a late export response after revision changes', async () => {
  const pending = deferred<ExportArtifact>();
  vi.mocked(api.createExport).mockReturnValue(pending.promise);
  const { rerender } = render(<ExportPanel caseId="case-1" revision={revision} dirty={false} />);
  await userEvent.click(screen.getByRole('button', { name: /create export/i }));
  rerender(<ExportPanel caseId="case-1" revision={{ id: 'rev-2' }} dirty={false} />);
  await act(async () => { pending.resolve(artifact); });
  expect(screen.queryByText('mask-hash')).not.toBeInTheDocument();
});
