import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';
import { api } from '../src/api/client';
import App from '../src/App';
import { useWorkspace } from '../src/state/workspace';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, listCases: vi.fn().mockResolvedValue([]) } };
});
vi.mock('../src/features/viewer/ViewerGrid', () => ({ ViewerGrid: () => <div>Viewer mock</div> }));

test('renders the NeuroAnnotate workspace shell', async () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: 'NeuroAnnotate' })).toBeInTheDocument();
  expect(screen.getByText('Research & portfolio software · Not for clinical use')).toBeInTheDocument();
  expect(await screen.findByText('No MRI cases yet')).toBeInTheDocument();
  expect(screen.getByText('Create a case using DWI, ADC, and FLAIR NIfTI volumes.')).toBeInTheDocument();
});

test('keeps the current case when dirty navigation is not confirmed', async () => {
  const cases = [
    { id: 'case-1', name: 'Case one', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true },
    { id: 'case-2', name: 'Case two', created_at: '', modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true },
  ];
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
