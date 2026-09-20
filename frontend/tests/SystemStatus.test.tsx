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

test('renders only safe DeepISLES identity facts for a ready GPU mode', () => {
  render(<SystemStatus health={{
    status: 'ok', service: 'neuroannotate-api', storage: 'ok', database: 'ok',
    inference: {
      mode: 'gpu', deepisles: 'ready', ready: true,
      service: 'neuroannotate-deepisles', service_version: '1.0.0',
      model_name: 'DeepISLES', model_version: '7658b608fc0d890cf14448ff3e58c47ad5c761e7',
      device: 'cuda:0', cuda_available: true,
    },
  }} />);
  expect(screen.getByText('DeepISLES model').parentElement).toHaveTextContent('DeepISLES modelDeepISLES');
  expect(screen.getByText('GPU device').parentElement).toHaveTextContent('GPU devicecuda:0');
});
