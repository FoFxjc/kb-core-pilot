import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Citation, citationText, TierBadge } from './Shared';

describe('citation', () => {
  it('uses the contract form with physical and printed pages', () => {
    expect(citationText({ doc_id: 'ocbc-group_ar_2025_en', page_range: [105, 105], page_label_range: ['103', '103'] }))
      .toBe('ocbc-group_ar_2025_en, physical page 105, printed page 103');
    expect(citationText({ doc_id: 'd', page_range: [98, 100], page_label_range: ['96', '98'] }))
      .toBe('d, physical page 98-100, printed page 96-98');
    expect(citationText({ doc_id: 'd', page_range: [4, 4], page_label_range: null }))
      .toBe('d, physical page 4, printed page n/a');
  });

  it('links to the document view at the first page', () => {
    render(<Citation source={{ doc_id: 'd', page_range: [98, 100], page_label_range: ['96', '98'] }} />);
    expect(screen.getByRole('link').getAttribute('href')).toBe('/ui/docs/d/pages/98');
  });

  it('labels each tier', () => {
    render(<TierBadge tier="fact" />);
    expect(screen.getByText('Fact').dataset.tier).toBe('fact');
  });
});
