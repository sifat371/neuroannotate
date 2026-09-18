import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { SystemStatus } from '../src/features/system/SystemStatus';

test('reports the expected neutral DeepISLES state when demo mode has no GPU service enabled', () => {
  render(<SystemStatus health={{
    status: 'ok', service: 'neuroannotate-api', storage: 'ok', database: 'ok',
    inference: { mode: 'demo', deepisles: 'not_enabled', ready: false },
  }} />);
  expect(screen.getByText('Backend').parentElement).toHaveTextContent('Backendok');
  expect(screen.getByText('Storage').parentElement).toHaveTextContent('Storageok');
  expect(screen.getByText('Database').parentElement).toHaveTextContent('Databaseok');
  expect(screen.getByText('Inference mode').parentElement).toHaveTextContent('Inference modedemo');
  expect(screen.getByText('GPU service').parentElement).toHaveTextContent('GPU servicenot enabled');
  expect(screen.getByText('DeepISLES readiness').parentElement).toHaveTextContent('DeepISLES readinessnot ready');
  expect(screen.getByText(/expected while demo mode is active/i)).toBeInTheDocument();
});
