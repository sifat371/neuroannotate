import type { SystemHealth } from '../../types/api';

type Props = { health: SystemHealth | null };

function label(value: string) {
  return value.replaceAll('_', ' ');
}

export function SystemStatus({ health }: Props) {
  const mode = health?.inference?.mode ?? 'unknown';
  const gpu = health?.inference?.deepisles ?? 'unavailable';
  const readiness = health?.inference?.ready ? 'ready' : 'not ready';
  return (
    <section className="panel system-status">
      <div className="panel-heading"><div><p className="eyebrow">System</p><h2>Status</h2></div></div>
      <dl>
        <div><dt>Backend</dt><dd>{health?.status ?? 'unavailable'}</dd></div>
        <div><dt>Storage</dt><dd>{health?.storage ?? 'unavailable'}</dd></div>
        <div><dt>Database</dt><dd>{health?.database ?? 'unavailable'}</dd></div>
        <div><dt>Inference mode</dt><dd>{mode}</dd></div>
        <div><dt>GPU service</dt><dd>{label(gpu)}</dd></div>
        <div><dt>DeepISLES readiness</dt><dd>{readiness}</dd></div>
      </dl>
      {mode === 'demo' && gpu === 'not_enabled' ? <p className="muted">GPU service not enabled is expected while demo mode is active.</p> : null}
    </section>
  );
}
