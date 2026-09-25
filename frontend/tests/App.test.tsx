import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import App from '../src/App';
import { useWorkspace } from '../src/state/workspace';
import type { SystemHealth } from '../src/types/api';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return {
    ...actual,
    api: {
      ...actual.api,
      listCases: vi.fn().mockResolvedValue([]),
      listInferenceJobs: vi.fn().mockResolvedValue([]),
      getInferenceJob: vi.fn(),
      createCase: vi.fn(),
      getSystemHealth: vi.fn(),
    },
  };
});
vi.mock('../src/features/viewer/ViewerGrid', () => ({
  ViewerGrid: ({ inference }: { inference: { segmentationId: string } | null }) => <div data-testid="viewer-segmentation">{inference?.segmentationId ?? 'none'}</div>,
}));

const demoHealth: SystemHealth = {
  status: 'ok', service: 'neuroannotate-api', storage: 'ok', database: 'ok',
  inference: { mode: 'demo', deepisles: 'not_enabled', ready: true },
};
const cases = [
  { id: 'case-1', name: 'Case one', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true },
  { id: 'case-2', name: 'Case two', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true },
];
const job = (id: string, caseId: string, status: 'queued' | 'running' | 'completed' | 'failed', segmentationId: string | null = null) => ({
  id, case_id: caseId, provider: 'demo', model_name: 'Demo', model_version: '1', service_version: '1', status,
  created_at: '2026-09-17T12:00:00Z', started_at: null, completed_at: null, segmentation_id: segmentationId,
  failure_category: status === 'failed' ? 'provider_runtime_failure' : null,
  error_message: status === 'failed' ? 'Provider failed' : null, provenance: {},
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  return { promise: new Promise<T>((done) => { resolve = done; }), resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listCases).mockResolvedValue([]);
  vi.mocked(api.listInferenceJobs).mockResolvedValue([]);
  vi.mocked(api.getSystemHealth).mockResolvedValue(demoHealth);
  useWorkspace.setState({ selectedCaseId: null, dirty: false, activeJobId: null, loadedSegmentationId: null, loadedRevisionId: null, baseRevisionId: null });
});

afterEach(() => {
  vi.useRealTimers();
});

test('renders the NeuroAnnotate workspace shell', async () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: 'NeuroAnnotate' })).toBeInTheDocument();
  expect(screen.getByText('Research & portfolio software · Not for clinical use')).toBeInTheDocument();
  expect(await screen.findByText('No MRI cases yet')).toBeInTheDocument();
  expect(screen.getByText('Create a case using DWI, ADC, and FLAIR NIfTI volumes.')).toBeInTheDocument();
});

test('keeps the current case when dirty navigation is not confirmed', async () => {
  vi.mocked(api.listCases).mockResolvedValue(cases);
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<App />);
  await screen.findByRole('button', { name: /case two/i });
  await act(async () => { useWorkspace.getState().setDirty(true); });
  await userEvent.click(screen.getByRole('button', { name: /case two/i }));
  expect(window.confirm).toHaveBeenCalled();
  expect(screen.getByRole('button', { name: /case one/i })).toHaveAttribute('aria-pressed', 'true');
});

test('adds a created case without discarding dirty edits when selection is declined', async () => {
  const created = { id: 'case-3', name: 'Created case', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true, annotation_space: 'DWI' as const, sources: [] };
  vi.mocked(api.listCases).mockResolvedValue(cases);
  vi.mocked(api.createCase).mockResolvedValue(created);
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole('button', { name: /case one/i });
  await act(async () => { useWorkspace.getState().setDirty(true); });
  await user.type(screen.getByLabelText('Case name'), 'Created case');
  await user.click(screen.getByRole('button', { name: /NIfTI triad/i }));
  await user.upload(screen.getByLabelText(/DWI NIfTI/i), new File(['dwi'], 'dwi.nii.gz'));
  await user.upload(screen.getByLabelText(/ADC NIfTI/i), new File(['adc'], 'adc.nii.gz'));
  await user.upload(screen.getByLabelText(/FLAIR NIfTI/i), new File(['flair'], 'flair.nii.gz'));
  await user.click(screen.getByRole('button', { name: 'Create Case' }));
  await screen.findByRole('button', { name: /created case/i });
  expect(window.confirm).toHaveBeenCalled();
  expect(screen.getByRole('button', { name: /case one/i })).toHaveAttribute('aria-pressed', 'true');
  expect(useWorkspace.getState().dirty).toBe(true);
});

test('restores the latest attempt separately from the newest usable segmentation', async () => {
  vi.mocked(api.listCases).mockResolvedValue([cases[0]]);
  vi.mocked(api.listInferenceJobs).mockResolvedValue([
    job('failed-new', 'case-1', 'failed'),
    job('completed-old', 'case-1', 'completed', 'seg-old'),
  ]);
  const { unmount } = render(<App />);
  expect(await screen.findByText('Failed')).toBeInTheDocument();
  expect(screen.getByText('Provider failed')).toBeInTheDocument();
  expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('seg-old');
  expect(useWorkspace.getState().activeJobId).toBe('failed-new');

  unmount();
  vi.mocked(api.listInferenceJobs).mockResolvedValue([job('failed-only', 'case-1', 'failed')]);
  useWorkspace.setState({ selectedCaseId: null, activeJobId: null, loadedSegmentationId: null });
  render(<App />);
  expect(await screen.findByText('Failed')).toBeInTheDocument();
  expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('none');
  expect(useWorkspace.getState().activeJobId).toBe('failed-only');
});

test('a completing background job does not replace dirty edits until explicit confirmed load', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listCases).mockResolvedValue([cases[0]]);
  vi.mocked(api.listInferenceJobs).mockResolvedValue([
    job('queued-new', 'case-1', 'queued'),
    job('completed-old', 'case-1', 'completed', 'seg-old'),
  ]);
  vi.mocked(api.getInferenceJob).mockResolvedValue(job('queued-new', 'case-1', 'completed', 'seg-new'));
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<App />);
  await waitFor(() => expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('seg-old'));
  await act(async () => { useWorkspace.getState().setDirty(true); });
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Load Segmentation' })).toBeInTheDocument());
  expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('seg-old');
  expect(useWorkspace.getState().dirty).toBe(true);

  await userEvent.click(screen.getByRole('button', { name: 'Load Segmentation' }));
  expect(confirm).toHaveBeenCalled();
  expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('seg-old');
  confirm.mockReturnValue(true);
  await userEvent.click(screen.getByRole('button', { name: 'Load Segmentation' }));
  expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('seg-new');
  expect(useWorkspace.getState().dirty).toBe(false);
});

test('refreshes inference health instead of keeping a first-boot unknown state forever', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.getSystemHealth).mockRejectedValueOnce(new Error('starting')).mockResolvedValue(demoHealth);
  render(<App />);
  await waitFor(() => expect(screen.getByText(/readiness is unknown/i)).toBeInTheDocument());
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  await waitFor(() => expect(api.getSystemHealth).toHaveBeenCalledTimes(2));
  expect(screen.queryByText(/readiness is unknown/i)).not.toBeInTheDocument();
});

test('ignores a prior case job response after switching cases', async () => {
  const first = deferred<ReturnType<typeof job>[]>();
  const second = deferred<ReturnType<typeof job>[]>();
  vi.mocked(api.listCases).mockResolvedValue(cases);
  vi.mocked(api.listInferenceJobs).mockImplementation((caseId) => caseId === 'case-1' ? first.promise : second.promise);
  render(<App />);
  await waitFor(() => expect(api.listInferenceJobs).toHaveBeenCalledWith('case-1'));
  await userEvent.click(screen.getByRole('button', { name: /case two/i }));
  await waitFor(() => expect(api.listInferenceJobs).toHaveBeenCalledWith('case-2'));
  await act(async () => { second.resolve([job('case-2-completed', 'case-2', 'completed', 'seg-case-2')]); });
  await waitFor(() => expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('seg-case-2'));
  await act(async () => { first.resolve([job('case-1-completed', 'case-1', 'completed', 'seg-case-1')]); });
  expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('seg-case-2');
  expect(useWorkspace.getState().activeJobId).toBe('case-2-completed');
});

test('ignores an unresolved job response after unmount', async () => {
  const pending = deferred<ReturnType<typeof job>[]>();
  vi.mocked(api.listCases).mockResolvedValue([cases[0]]);
  vi.mocked(api.listInferenceJobs).mockImplementation(() => pending.promise);
  const { unmount } = render(<App />);
  await waitFor(() => expect(api.listInferenceJobs).toHaveBeenCalledWith('case-1'));
  unmount();
  await act(async () => { pending.resolve([job('late', 'case-1', 'completed', 'seg-late')]); });
  expect(useWorkspace.getState().activeJobId).toBeNull();
});
