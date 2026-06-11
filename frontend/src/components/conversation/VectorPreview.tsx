// Renders an AI draft body with "vector preview" citation highlights when
// citations are present, and plain body when they're empty (contract rule).
//
// `citations` is a JSON blob (DraftResponse.citations) produced by a future
// vector/RAG layer (Track B). Its exact shape isn't frozen, so this renderer is
// defensive: it accepts the common shapes and degrades to a plain body when it
// can't find anything to highlight. Never throws on malformed input.

import { useMemo } from 'react';
import { cn } from '@/lib/utils';

export interface NormalizedCitation {
  /** The verbatim text to highlight inside the body, if any. */
  quote: string | null;
  /** A short source/label shown on hover + in the citation list. */
  label: string | null;
}

/** Best-effort normalization of an unknown citations JSON value. */
export function normalizeCitations(raw: unknown): NormalizedCitation[] {
  if (!raw) return [];
  let value: unknown = raw;
  if (typeof raw === 'string') {
    try {
      value = JSON.parse(raw);
    } catch {
      // A plain string citation = one labelled source, nothing to highlight.
      return [{ quote: null, label: raw }];
    }
  }
  const obj = value as Record<string, unknown> | null;
  const arr: unknown[] = Array.isArray(value)
    ? value
    : obj && Array.isArray(obj.citations)
      ? (obj.citations as unknown[])
      : obj && typeof obj === 'object'
        ? [obj]
        : [];

  return arr
    .map((c): NormalizedCitation | null => {
      if (typeof c === 'string') return { quote: c, label: null };
      if (c && typeof c === 'object') {
        const o = c as Record<string, unknown>;
        const quote =
          (o.quote as string) ??
          (o.text as string) ??
          (o.snippet as string) ??
          (o.span as string) ??
          null;
        const label =
          (o.label as string) ??
          (o.source as string) ??
          (o.title as string) ??
          (o.reason as string) ??
          null;
        if (!quote && !label) return null;
        return { quote: quote ?? null, label: label ?? null };
      }
      return null;
    })
    .filter((c): c is NormalizedCitation => c !== null);
}

interface VectorPreviewProps {
  body: string;
  citations?: unknown;
  className?: string;
}

/**
 * Splits the body so every citation `quote` found in it is wrapped in a
 * highlight span (the "vector preview"). Quotes that don't appear verbatim are
 * still surfaced as labelled chips below. Empty citations => plain body.
 */
export function VectorPreview({ body, citations, className }: VectorPreviewProps) {
  const normalized = useMemo(() => normalizeCitations(citations), [citations]);
  const highlightable = useMemo(
    () => normalized.filter((c) => c.quote && body.includes(c.quote)),
    [normalized, body],
  );
  const unanchored = useMemo(
    () => normalized.filter((c) => !c.quote || !body.includes(c.quote)),
    [normalized, body],
  );

  const segments = useMemo(() => {
    if (highlightable.length === 0) {
      return [{ text: body, citation: null as NormalizedCitation | null }];
    }
    // Build a regex of all quotes, longest first to avoid nested partials.
    const quotes = highlightable
      .map((c) => c.quote as string)
      .sort((a, b) => b.length - a.length);
    const escaped = quotes.map((q) => q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const re = new RegExp(`(${escaped.join('|')})`, 'g');
    const out: { text: string; citation: NormalizedCitation | null }[] = [];
    let lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(body)) !== null) {
      if (m.index > lastIndex) {
        out.push({ text: body.slice(lastIndex, m.index), citation: null });
      }
      const matched = m[0];
      const citation = highlightable.find((c) => c.quote === matched) || null;
      out.push({ text: matched, citation });
      lastIndex = m.index + matched.length;
    }
    if (lastIndex < body.length) {
      out.push({ text: body.slice(lastIndex), citation: null });
    }
    return out;
  }, [body, highlightable]);

  return (
    <div className={cn('space-y-3', className)}>
      <div className="whitespace-pre-wrap text-sm leading-relaxed text-fg-200">
        {segments.map((seg, i) =>
          seg.citation ? (
            <mark
              key={i}
              title={seg.citation.label || 'Grounded from your knowledge base'}
              className="rounded-sm bg-rust-900/40 px-0.5 text-fg-100 underline decoration-dotted decoration-rust-500/60 underline-offset-2"
            >
              {seg.text}
            </mark>
          ) : (
            <span key={i}>{seg.text}</span>
          ),
        )}
      </div>

      {(highlightable.length > 0 || unanchored.length > 0) && (
        <ul className="space-y-1 border-t border-border pt-2">
          {[...highlightable, ...unanchored].map((c, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-fg-400">
              <span className="mt-0.5 font-mono text-[10px] font-semibold tracking-wider text-rust-500">
                SRC
              </span>
              <span>{c.label || c.quote}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
