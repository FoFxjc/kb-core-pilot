import { describe, expect, it } from 'vitest';
import { boxStyle, typeColour } from './regions';

describe('boxStyle', () => {
  it('scales a bbox in points to percentages of the page', () => {
    expect(boxStyle([0, 0, 100, 50], 200, 100)).toEqual({ left: '0%', top: '0%', width: '50%', height: '50%' });
    expect(boxStyle([50, 25, 150, 75], 200, 100)).toEqual({ left: '25%', top: '25%', width: '50%', height: '50%' });
  });

  it('works on a real A4 page in points', () => {
    const s = boxStyle([36.8504, 42.5199, 372.0304, 60.54162], 595.276, 793.701);
    expect(s.left).toBe('6.19%');
    expect(s.top).toBe('5.357%');
    expect(s.width).toBe('56.307%');
    expect(s.height).toBe('2.271%');
  });
});

describe('typeColour', () => {
  it('gives known types distinct colours and unknown types a stable one', () => {
    expect(typeColour('text')).not.toBe(typeColour('table'));
    expect(typeColour('something_new')).toBe(typeColour('something_new'));
  });
});
