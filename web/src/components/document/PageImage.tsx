// The page image with its region boxes. Boxes are positioned in percent of the page, so they follow the image size;
// each region type has a colour and a checkbox, and hovering a box shows its type, reading order and text.
import { useMemo, useState } from 'react';
import type { Region } from '../../api/client';
import { boxStyle, typeColour } from './regions';

export function PageImage({ src, regions, width, height, hidden, onToggleType }: {
  src: string;
  regions: Region[];
  width: number | null;
  height: number | null;
  hidden: Set<string>;
  onToggleType: (type: string) => void;
}) {
  const [hover, setHover] = useState<Region | null>(null);
  const [imageState, setImageState] = useState<'loading' | 'loaded' | 'error'>('loading');
  const types = useMemo(() => [...new Set(regions.map((r) => r.type))].sort(), [regions]);
  const sized = !!width && !!height;
  const visible = sized ? regions.filter((r) => !hidden.has(r.type)) : [];

  return (
    <div className="page-image-area">
      <fieldset className="region-types">
        <legend>Region boxes</legend>
        {types.length === 0 && <span className="muted">No regions on this page.</span>}
        {types.map((t) => (
          <label key={t} className="region-type" style={{ borderColor: typeColour(t) }}>
            <input type="checkbox" checked={!hidden.has(t)} onChange={() => onToggleType(t)} />
            <span className="swatch" style={{ background: typeColour(t) }} />
            {t} <span className="muted">({regions.filter((r) => r.type === t).length})</span>
          </label>
        ))}
        {!sized && regions.length > 0 && <span className="muted">The page size is unknown, so boxes are not drawn.</span>}
      </fieldset>
      <div className="page-frame">
        {/* key on src: a new page starts in the loading state again */}
        <img key={src} src={src} alt="Page image" className="page-img" data-state={imageState}
          onLoad={() => setImageState('loaded')} onError={() => setImageState('error')} />
        {imageState === 'error' && <div className="error-banner" role="alert">The page image could not be loaded.</div>}
        {visible.map((r) => (
          <div
            key={r.region_id}
            className={`region-box${hover?.region_id === r.region_id ? ' hovered' : ''}`}
            data-region-type={r.type}
            style={{ ...boxStyle(r.bbox, width!, height!), borderColor: typeColour(r.type) }}
            onMouseEnter={() => setHover(r)}
            onMouseLeave={() => setHover((h) => (h?.region_id === r.region_id ? null : h))}
          />
        ))}
        {hover && sized && !hidden.has(hover.type) && (
          <div className="region-tip" role="tooltip"
            style={{ left: boxStyle(hover.bbox, width!, height!).left, top: `${Math.min(hover.bbox[3] / height! * 100, 92)}%` }}>
            <strong style={{ color: typeColour(hover.type) }}>{hover.type}{hover.subtype ? ` / ${hover.subtype}` : ''}</strong>
            {' '}· reading order {hover.reading_order}
            {hover.text && <div className="region-tip-text">{hover.text}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
