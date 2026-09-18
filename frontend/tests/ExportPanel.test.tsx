import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import { ExportPanel } from '../src/features/exports/ExportPanel';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, createExport: vi.fn() } };
});

const revision = { id: 'rev-1', case_id: 'case-1', source_inference_id: 'job-1', source_segmentation_id: 'seg-1', parent_revision_id: null, sha256: 'revision-hash', edit_stats: {}, note: null, created_at: '2026-09-17T12:00:00Z' };

beforeEach(() => vi.clearAllMocks());

test('disables export while unsaved edits exist', () => {
  render(<ExportPanel caseId="case-1" revision={revision} dirty />);
  expect(screen.getByRole('button', { name: /create export/i })).toBeDisabled();
  expect(screen.getByText(/save your annotation changes/i)).toBeInTheDocument();
});

test('creates an export only from the selected saved revision and shows DWI-space output links', async () => {
  vi.mocked(api.createExport).mockResolvedValue({ id: 'export-1', case_id: 'case-1', revision_id: 'rev-1', mask_sha256: 'mask-hash', created_at: '', mask_url: '/mask', provenance_url: '/provenance', bundle_url: '/bundle' });
  render(<ExportPanel caseId="case-1" revision={revision} dirty={false} />);
  await userEvent.click(screen.getByRole('button', { name: /create export/i }));
  await waitFor(() => expect(api.createExport).toHaveBeenCalledWith('case-1', 'rev-1'));
  expect(screen.getByText(/DWI native annotation space/i)).toBeInTheDocument();
  expect(screen.getByText('mask-hash')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /download bundle/i })).toHaveAttribute('href', expect.stringContaining('/bundle'));
});
