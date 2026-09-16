import { forwardRef, type MouseEvent } from 'react';

type Props = { label: string; orientation: string };

export const Viewport = forwardRef<HTMLDivElement, Props>(function Viewport({ label, orientation }, ref) {
  return (
    <div className="viewport-shell">
      <div className="viewport-label"><span>{orientation}</span><span className="live-dot">●</span></div>
      <div ref={ref} className="viewport-canvas" aria-label={label} onContextMenu={(event: MouseEvent<HTMLDivElement>) => event.preventDefault()} />
    </div>
  );
});
