import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import App from '../src/App';
import { useWorkspace } from '../src/state/workspace';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return {
    ...actual,
    api: {
      ...actual.api,
      listCases: vi.fn().mockResolvedValue([]),
      listInferenceJobs: vi.fn().mockResolvedValue([]),
      createCase: vi.fn(),
      getSystemHealth: vi.fn().mockResolvedValue({ status: 'ok', service: 'neuroannotate-api' }),
    },
  };
});
vi.mock('../src/features/viewer/ViewerGrid', () => ({
  ViewerGrid: ({ inference }: { inference: { segmentationId: string } | null }) => <div data-testid="viewer-segmentation">{inference?.segmentationId ?? 'none'}</div>,
}));

const cases = [
  { id: 'case-1', name: 'Case one', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true },
  { id: 'case-2', name: 'Case two', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true },
];
const job = (id: string, caseId: string, status: 'queued' | 'running' | 'completed' | 'failed', segmentationId: string | null = null) => ({
  id, case_id: caseId, provider: 'demo', model_name: 'Demo', model_version: '1', service_version: '1', status,
  created_at: '2026-09-17T12:00:00Z', started_at: null, completed_at: null, segmentation_id: segmentationId,
  failure_category: null, error_message: null, provenance: {},
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  return { promise: new Promise<T>((done) => { resolve = done; }), resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listCases).mockResolvedValue([]);
  vi.mocked(api.listInferenceJobs).mockResolvedValue([]);
  vi.mocked(api.getSystemHealth).mockResolvedValue({ status: 'ok', service: 'neuroannotate-api' });
  useWorkspace.setState({ selectedCaseId: null, dirty: false, activeJobId: null, loadedSegmentationId: null, loadedRevisionId: null, baseRevisionId: null });
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
  useWorkspace.setState({ selectedCaseId: null, dirty: false });
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
  await user.upload(screen.getByLabelText(/DWI NIfTI/i), new File(['dwi'], 'dwi.nii.gz'));
  await user.upload(screen.getByLabelText(/ADC NIfTI/i), new File(['adc'], 'adc.nii.gz'));
  await user.upload(screen.getByLabelText(/FLAIR NIfTI/i), new File(['flair'], 'flair.nii.gz'));
  await user.click(screen.getByRole('button', { name: 'Create Case' }));
  await screen.findByRole('button', { name: /created case/i });
  expect(window.confirm).toHaveBeenCalled();
  expect(screen.getByRole('button', { name: /case one/i })).toHaveAttribute('aria-pressed', 'true');
  expect(useWorkspace.getState().dirty).toBe(true);
});

test('restores an active job before completed history and otherwise uses the newest completed segmentation', async () => {
  vi.mocked(api.listCases).mockResolvedValue([cases[0]]);
  vi.mocked(api.listInferenceJobs).mockResolvedValue([
    job('failed-old', 'case-1', 'failed'),
    job('completed-old', 'case-1', 'completed', 'seg-old'),
    job('queued-new', 'case-1', 'queued'),
    job('completed-new', 'case-1', 'completed', 'seg-new'),
  ]);
  const { unmount } = render(<App />);
  await screen.findByText('Queued');
  expect(useWorkspace.getState().activeJobId).toBe('queued-new');
  expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('none');

  unmount();
  vi.mocked(api.listInferenceJobs).mockResolvedValue([
    job('failed-old', 'case-1', 'failed'),
    job('completed-old', 'case-1', 'completed', 'seg-old'),
    job('completed-new', 'case-1', 'completed', 'seg-new'),
  ]);
  useWorkspace.setState({ selectedCaseId: null, activeJobId: null, loadedSegmentationId: null });
  render(<App />);
  await waitFor(() => expect(screen.getByTestId('viewer-segmentation')).toHaveTextContent('seg-new'));
  expect(useWorkspace.getState().activeJobId).toBe('completed-new');
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
