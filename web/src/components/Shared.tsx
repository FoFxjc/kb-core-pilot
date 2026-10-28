// Components shared by the three views: layer badge, citation link, internal link, error banner, loading state.
import type { ReactNode } from 'react';
import type { Source, Tier } from '../api/client';
import { href, onLinkClick, type Route } from '../lib/router';

const TIER_LABEL: Record<Tier, string> = { fact: 'Fact', link: 'Link', structure: 'Structure', text: 'Text' };
const TIER_HINT: Record<Tier, string> = {
  fact: 'Canonical fact with provenance; still read the source before citing',
  link: 'Section tagged with a concept in the query',
  structure: 'Title hit with an informative query term',
  text: 'Body-text hit; a lead only',
};

export function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span className={`badge tier-${tier}`} title={TIER_HINT[tier]} data-tier={tier}>
      {TIER_LABEL[tier]}
    </span>
  );
}

export function Link({ to, children, className }: { to: Route; children: ReactNode; className?: string }) {
  return (
    <a href={href(to)} onClick={onLinkClick} className={className}>
      {children}
    </a>
  );
}

/** "(doc_id, physical page s, printed page p)": the contract's citation form, linking to the document view. */
export function citationText(s: Pick<Source, 'doc_id' | 'page_range' | 'page_label_range'>): string {
  const [start, end] = s.page_range ?? [null, null];
  const [ls, le] = s.page_label_range ?? [null, null];
  const phys = start === null ? '?' : start === end ? `${start}` : `${start}-${end}`;
  const printed = ls === null || ls === undefined ? 'n/a' : ls === le || le === null ? `${ls}` : `${ls}-${le}`;
  return `${s.doc_id}, physical page ${phys}, printed page ${printed}`;
}

export function Citation({ source }: { source: Pick<Source, 'doc_id' | 'page_range' | 'page_label_range'> }) {
  const page = source.page_range?.[0];
  return (
    <Link to={{ view: 'document', docId: source.doc_id, page: page ?? undefined }} className="citation">
      ({citationText(source)})
    </Link>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="error-banner" role="alert">
      {msg}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <div className="loading">Loading {what}…</div>;
}
