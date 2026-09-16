import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { CaseSidebar } from '../src/features/cases/CaseSidebar';

const ready = {
  id: 'case-1', name: 'NeuroAnnotate Demo', created_at: '2026-09-16T00:00:00Z',
  modalities: ['DWI', 'ADC', 'FLAIR'] as Array<'DWI' | 'ADC' | 'FLAIR'>, ready_for_inference: true,
};

describe('CaseSidebar', () => {
  test('selects a ready demo case', async () => {
    const onSelect = vi.fn();
    render(<CaseSidebar cases={[ready]} selectedCaseId={null} onSelect={onSelect} />);
    expect(screen.getByText('NeuroAnnotate Demo')).toBeInTheDocument();
    expect(screen.getByText('Ready for AI')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /NeuroAnnotate Demo/i }));
    expect(onSelect).toHaveBeenCalledWith('case-1');
  });

  test('shows missing modalities', () => {
    render(<CaseSidebar cases={[{ ...ready, modalities: ['DWI'], ready_for_inference: false }]} selectedCaseId={null} onSelect={() => undefined} />);
    expect(screen.getByText('Needs ADC/FLAIR')).toBeInTheDocument();
  });
});
