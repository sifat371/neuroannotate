import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { RevisionPanel } from '../src/features/revisions/RevisionPanel';

test('save revision is disabled without an active segmentation', () => {
  render(<RevisionPanel caseId="c1" sourceInferenceId={null} segmentation={null} selectedRevisionId={null} onSelectedRevisionId={() => undefined} onLoadRevision={() => undefined} />);
  expect(screen.getByRole('button', { name: 'Save Revision' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Export Annotation' })).toBeDisabled();
});
