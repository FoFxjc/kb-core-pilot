// Region boxes: PDF-point bboxes (origin top left) scaled to percentages of the page, and one colour per region type.
import type { CSSProperties } from 'react';

const pct = (v: number) => `${Number((v * 100).toFixed(3))}%`;

/** Position a [x0, y0, x1, y1] box in points on a width x height page as percentages of the displayed image. */
export function boxStyle(bbox: [number, number, number, number], width: number, height: number): CSSProperties {
  const [x0, y0, x1, y1] = bbox;
  return {
    left: pct(x0 / width),
    top: pct(y0 / height),
    width: pct((x1 - x0) / width),
    height: pct((y1 - y0) / height),
  };
}

const KNOWN: Record<string, string> = {
  text: '#2456c7',
  title: '#b3261e',
  heading: '#d4590b',
  table: '#1f7a4d',
  picture: '#7a4fb5',
  list: '#0e7c86',
  caption: '#c2185b',
  formula: '#5d4037',
  logo: '#8d6e00',
  page_header: '#6b7079',
  page_footer: '#6b7079',
};
const OTHERS = ['#00838f', '#6a1b9a', '#ad1457', '#558b2f', '#4e342e', '#283593'];

export function typeColour(type: string): string {
  if (KNOWN[type]) return KNOWN[type];
  let h = 0;
  for (const ch of type) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return OTHERS[h % OTHERS.length];
}
