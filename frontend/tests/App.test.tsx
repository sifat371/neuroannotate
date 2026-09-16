import { render, screen } from '@testing-library/react';
import { beforeEach, test, vi } from 'vitest';
import App from '../src/App';

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, api: { ...actual.api, listCases: vi.fn().mockResolvedValue([]) } };
});
vi.mock('../src/features/viewer/ViewerGrid', () => ({ ViewerGrid: () => <div>Viewer mock</div> }));

test('renders the NeuroAnnotate workspace shell', async () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: 'NeuroAnnotate' })).toBeInTheDocument();
  expect(screen.getByText(/Not for clinical use/i)).toBeInTheDocument();
});
