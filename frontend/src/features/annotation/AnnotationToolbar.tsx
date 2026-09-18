import { useEffect, useState } from 'react';
import type { EditableSegmentation } from '../../cornerstone/segmentation';
import type { EditingTool } from '../../state/workspace';

const tools: Array<[EditingTool, string]> = [
  ['brush', 'Brush'], ['erase', 'Erase'], ['pan', 'Pan'], ['zoom', 'Zoom'], ['windowLevel', 'Window/Level'],
];

type Props = { segmentation: EditableSegmentation | null; activeTool: EditingTool; onToolChange: (tool: EditingTool) => void; baseLabel?: string; unsavedEditCount?: number };

export function AnnotationToolbar({ segmentation, activeTool, onToolChange, baseLabel = 'No segmentation', unsavedEditCount = 0 }: Props) {
  const [brushSize, setBrushSize] = useState(12);
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || !segmentation) return;
      if (event.key.toLowerCase() === 'z' && !event.shiftKey) { event.preventDefault(); segmentation.undo(); }
      else if ((event.key.toLowerCase() === 'z' && event.shiftKey) || event.key.toLowerCase() === 'y') { event.preventDefault(); segmentation.redo(); }
    }
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  }, [segmentation]);

  return (
    <div className="annotation-toolbar" aria-label="Annotation tools">
      <span className="annotation-base">Base: {baseLabel}</span>
      {tools.map(([key, label]) => (
        <button key={key} type="button" className={activeTool === key ? 'tool-button active' : 'tool-button'} disabled={!segmentation && (key === 'brush' || key === 'erase')} onClick={() => onToolChange(key)}>{label}</button>
      ))}
      <span className="tool-separator" />
      <button className="tool-button" type="button" disabled={!segmentation} onClick={() => segmentation?.undo()}>Undo</button>
      <button className="tool-button" type="button" disabled={!segmentation} onClick={() => segmentation?.redo()}>Redo</button>
      <label className="brush-size">Brush size {brushSize}<input aria-label="Brush size" type="range" min="1" max="40" value={brushSize} onChange={(event) => { const size = Number(event.target.value); setBrushSize(size); segmentation?.setBrushSize(size); }} disabled={!segmentation} /></label>
      <span className="dirty-count">{unsavedEditCount === 0 ? 'No unsaved changes' : `${unsavedEditCount} unsaved ${unsavedEditCount === 1 ? 'edit' : 'edits'}`}</span>
    </div>
  );
}
