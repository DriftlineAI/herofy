// VoiceIndex — the Voice tab content in the Handbook
// Shows pinned Core Voice hero card + Foundation cards

import { NavLink } from 'react-router-dom';
import { useVoiceDocs, type VoiceDoc } from '@/lib/dataconnect-hooks';
import { Timestamp } from '@/components/ui/huds';
import { Star, ChevronRight } from 'lucide-react';

// Section opener component
function SectionOpener({ label, count }: { label: string; count?: number }) {
  return (
    <div className="pb-section-opener" style={{ marginBottom: 18 }}>
      <div className="pb-section-opener__seed" />
      <span className="pb-section-opener__label">
        {label}{count !== undefined ? ` · ${count}` : ''}
      </span>
      <div className="pb-section-opener__line" />
    </div>
  );
}

// Core Voice hero card (pinned at top)
function VoiceHeroCard({ doc }: { doc: VoiceDoc }) {
  // Extract pull quote - look for quotes that start a line (standalone pull quotes)
  const pullQuoteMatch = doc.body.match(/(?:^|\n)\s*"([^"]{30,})"/m);
  const pullQuote = pullQuoteMatch ? pullQuoteMatch[1] : null;

  // Get clean paragraphs from body, excluding NEVER DRAFT sections and the pull quote line
  const cleanBody = doc.body
    .replace(/⌐ NEVER[\s\S]*$/i, '')
    .replace(/(?:^|\n)\s*"[^"]{30,}"\s*(?:\n|$)/gm, '\n\n')
    .trim();
  const paragraphs = cleanBody.split('\n\n').filter(p => p.trim() && !p.startsWith('⌐') && !p.startsWith('"'));

  // First paragraph is the main excerpt
  const mainExcerpt = paragraphs[0]?.trim() || '';

  return (
    <NavLink to={`/app/handbook/voice/${doc.slug}`} className="hud-pane hud-pane--compact group block mb-6">
      {/* Header */}
      <div className="hud-pane__header">
        <span className="hud-pane__pulse" />
        <span className="hud-pane__label">
          CORE VOICE · HOW SIDEKICK ALWAYS SOUNDS
        </span>
        <span className="grow" />
        <span className="hud-pane__ref">
          <Timestamp time={doc.updated_at} />
        </span>
      </div>

      {/* Body */}
      <div className="hud-pane__body">
        <h2 className="font-display text-3xl text-fg-100 mb-4 group-hover:text-accent transition-colors">
          {doc.title}
        </h2>
        <p className="text-fg-200 leading-relaxed mb-4 max-w-[720px]">
          {mainExcerpt}
        </p>
        {pullQuote && (
          <div className="border-l-2 border-accent pl-4 py-1 mb-4 max-w-[640px]">
            <p className="font-serif italic text-fg-100">
              "{pullQuote}"
            </p>
          </div>
        )}
        <div className="flex flex-wrap gap-4 text-[10px] font-mono uppercase tracking-widest text-fg-400 pt-4 border-t border-rule">
          <span className="flex items-center gap-1">
            <Star className="w-3 h-3 text-accent" />
            EVERY OTHER VOICE DOC
          </span>
          <span>
            <strong className="text-signal-ok font-bold">{doc.used_in_drafts_today}</strong> DRAFTS
          </span>
          <span className="ml-auto text-accent font-bold flex items-center gap-1">
            OPEN EDITOR <ChevronRight className="w-3 h-3" />
          </span>
        </div>
      </div>
    </NavLink>
  );
}

// Foundation card with chapter number
function FoundationCard({ doc, index }: { doc: VoiceDoc; index: number }) {
  const chapterNum = doc.chapter_num || (index + 1);
  const formattedNum = chapterNum.toString().padStart(2, '0');

  // Get the first paragraph of the body as a more complete excerpt
  const cleanBody = doc.body.replace(/⌐ NEVER[\s\S]*$/i, '').trim();
  const firstParagraph = cleanBody.split('\n\n')[0]?.trim() || '';
  // Truncate if too long
  const excerpt = firstParagraph.length > 200
    ? firstParagraph.substring(0, 200).replace(/\s+\S*$/, '') + '…'
    : firstParagraph;

  return (
    <NavLink to={`/app/handbook/voice/${doc.slug}`} className="hud-pane hud-pane--compact group block mb-3">
      {/* Header */}
      <div className="hud-pane__header">
        <span className="hud-pane__label">
          CH {formattedNum} · FOUNDATION
        </span>
        <span className="grow" />
        <span className="hud-pane__ref">
          <Timestamp time={doc.updated_at} />
        </span>
      </div>

      {/* Body */}
      <div className="hud-pane__body">
        <div className="flex gap-6">
          <div className="font-display text-4xl text-fg-400 group-hover:text-accent transition-colors w-16 flex-shrink-0">
            {formattedNum}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-display text-xl text-fg-100 mb-2 group-hover:text-accent transition-colors">
              {doc.title}
            </h3>
            <p className="font-serif italic text-fg-300 text-sm leading-relaxed mb-3 max-w-[680px]">
              "{excerpt}"
            </p>
            <div className="flex flex-wrap gap-4 text-[9px] font-mono uppercase tracking-widest text-fg-400">
              <span className="flex items-center gap-1">
                <span className="text-accent">→</span> ALL PLAYBOOKS
              </span>
              <span>
                {doc.affects_surfaces ? JSON.parse(doc.affects_surfaces).length : 0} SURFACES
              </span>
            </div>
          </div>
        </div>
      </div>
    </NavLink>
  );
}

// Loading skeleton
function VoiceSkeleton() {
  return (
    <div className="space-y-4">
      {/* Hero skeleton */}
      <div className="hud-pane animate-pulse">
        <div className="hud-pane__header">
          <div className="h-3 w-48 bg-surface-2 rounded" />
        </div>
        <div className="hud-pane__body">
          <div className="h-8 w-3/4 bg-surface-2 rounded mb-4" />
          <div className="h-5 w-full bg-surface-2 rounded mb-2" />
          <div className="h-5 w-2/3 bg-surface-2 rounded" />
        </div>
      </div>
      {/* Foundation skeletons */}
      {[1, 2, 3].map(i => (
        <div key={i} className="hud-pane animate-pulse">
          <div className="hud-pane__header">
            <div className="h-3 w-32 bg-surface-2 rounded" />
          </div>
          <div className="hud-pane__body flex gap-6">
            <div className="h-12 w-12 bg-surface-2 rounded" />
            <div className="space-y-2 flex-1">
              <div className="h-5 w-2/3 bg-surface-2 rounded" />
              <div className="h-4 w-full bg-surface-2 rounded" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Empty state
function VoiceEmptyState() {
  return (
    <div className="text-center py-16">
      <h3 className="font-display text-2xl text-fg-100 mb-4">No voice documents yet</h3>
      <p className="text-fg-400 mb-6 max-w-md mx-auto">
        Voice documents define how Sidekick communicates with your customers.
        Create your Core Voice to get started.
      </p>
      <button className="text-[10px] font-mono uppercase tracking-widest px-6 py-3 border border-dashed border-border text-fg-400 hover:text-accent hover:border-accent transition-colors">
        + Create Core Voice
      </button>
    </div>
  );
}

export function VoiceIndex() {
  const { data, isLoading, error } = useVoiceDocs();

  if (isLoading) {
    return <VoiceSkeleton />;
  }

  if (error) {
    return (
      <div className="text-center py-16 text-signal-bad">
        Error loading voice documents: {error.message}
      </div>
    );
  }

  if (!data || data.count === 0) {
    return <VoiceEmptyState />;
  }

  const { core, foundations, scenarios } = data;

  return (
    <div>
      {/* Core Voice hero */}
      {core && <VoiceHeroCard doc={core} />}

      {/* Foundations section */}
      {foundations.length > 0 && (
        <>
          <SectionOpener label="FOUNDATIONS" count={foundations.length} />
          <p className="font-serif italic text-sm text-fg-400 mb-5 max-w-[720px] leading-relaxed">
            Broader principles — how we think, what we believe, what we never do.
            Sidekick reads these before drafting anything customer-facing.
          </p>
          {foundations.map((doc, i) => (
            <FoundationCard key={doc.id} doc={doc} index={i} />
          ))}
        </>
      )}

      {/* Scenarios section (if any) */}
      {scenarios.length > 0 && (
        <>
          <SectionOpener label="SCENARIO VOICES" count={scenarios.length} />
          <p className="font-serif italic text-sm text-fg-400 mb-5 max-w-[720px] leading-relaxed">
            Scenario voices inherit from Core and adjust tone for specific moments
            — like re-engagement emails or renewal conversations.
          </p>
          {scenarios.map((doc, i) => (
            <FoundationCard key={doc.id} doc={doc} index={i} />
          ))}
        </>
      )}

      {/* Add new foundation hint */}
      <p className="font-serif italic text-sm text-fg-400 mt-9 max-w-[720px] leading-relaxed">
        Need a more specific tonal recipe — say, exactly how to write a save-the-account email?
        Add a <span className="text-accent not-italic font-mono text-[11px] tracking-widest uppercase">scenario voice</span> that inherits from these foundations and adjusts tone for the moment.
      </p>
    </div>
  );
}

export default VoiceIndex;
