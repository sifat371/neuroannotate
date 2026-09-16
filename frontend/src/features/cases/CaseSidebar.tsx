import type { CaseSummary } from '../../types/api';

type Props = {
  cases: CaseSummary[];
  selectedCaseId: string | null;
  onSelect: (id: string) => void;
  loading?: boolean;
};

export function CaseSidebar({ cases, selectedCaseId, onSelect, loading = false }: Props) {
  return (
    <section className="panel case-sidebar" aria-label="Cases">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Workspace</p>
          <h2>Cases</h2>
        </div>
        <span className="count-pill">{cases.length}</span>
      </div>
      {loading ? <p className="muted">Loading cases…</p> : null}
      <div className="case-list">
        {cases.map((item) => {
          const missing = (['DWI', 'ADC', 'FLAIR'] as const).filter((m) => !item.modalities.includes(m));
          return (
            <button
              key={item.id}
              type="button"
              className={`case-card ${selectedCaseId === item.id ? 'selected' : ''}`}
              onClick={() => onSelect(item.id)}
              aria-pressed={selectedCaseId === item.id}
            >
              <span className="case-name">{item.name}</span>
              <span className={`readiness ${item.ready_for_inference ? 'ready' : 'needs'}`}>
                {item.ready_for_inference ? 'Ready for AI' : `Needs ${missing.join('/')}`}
              </span>
              <span className="modality-row">{item.modalities.length ? item.modalities.join(' · ') : 'No volumes yet'}</span>
            </button>
          );
        })}
        {!loading && cases.length === 0 ? <p className="empty-state">Create a case or seed the demo workspace.</p> : null}
      </div>
    </section>
  );
}
