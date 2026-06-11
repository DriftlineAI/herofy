// Play layout — the need-open view for a *threadless proactive play* (e.g. a
// renewal_at_risk save play). Per the conversation reframe: route the need-open
// view by what the need IS, not by whether a thread exists. A play is the
// pre-conversation state; this renders the brief + the ordered save-play steps
// (the orchestrator's RiskBrief / RiskPlayStep artifact) plus a context rail and
// an "Open compose" CTA that graduates the play into a conversation.
//
// Mock-free: brief + steps come from `useRiskBriefsForCustomer`; customer context
// from `useCustomer`. When no brief row exists yet (Track B may not have produced
// one), it degrades to `need.lede` / `need.agent_reasoning` — clean, never empty-noise.

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, Check, Clock, PenLine, MessageSquare } from 'lucide-react';
import { RefCode, Timestamp, Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import {
  useNeed,
  useRiskBriefsForCustomer,
  useCustomer,
} from '@/lib/dataconnect-hooks';
import { RiskSavePlayCard } from '@/components/customer/RiskSavePlayCard';
import { SidekickObserved } from '@/components/sidekick/SidekickAtoms';
import { ContextRail } from './ContextRail';
import { DraftPanel } from './DraftPanel';
import type { RawDraft } from './DraftPanel';
import { needSeverity, severityText } from './conversationUtils';

type Need = NonNullable<ReturnType<typeof useNeed>['data']>['need'];

function formatTime(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  const hours = Math.floor(diffMs / 3600000);
  const days = Math.floor(diffMs / 86400000);
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days === 1) return '1d ago';
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** Human title for the play header, e.g. "Renewal at risk — save play ready". */
function playTitle(needType: string, customerName: string): string {
  const label = needType
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
  return `${customerName}: ${label.toLowerCase()} — save play ready`;
}

interface NeedPlayLayoutProps {
  need: Need;
  onResolve: () => void;
  onSnooze: () => void;
  /**
   * When true: strips the internal right-rail column (ContextRail, Sidekick note,
   * CTAs). The parent Conversations layout renders that content in its own right
   * pane via PlayRailContent. Compose starts open so the user can act immediately.
   */
  embedded?: boolean;
}

/**
 * The Play layout. Renders the correlated RiskBrief (brief + ordered save-play
 * steps) for a threadless play need, with a customer context rail and an
 * "Open compose" CTA (the graduation entry point into the existing compose path).
 */
export function NeedPlayLayout({ need, onResolve, onSnooze, embedded }: NeedPlayLayoutProps) {
  const navigate = useNavigate();
  const customerId = need.customer?.id || null;

  // Brief + ordered steps for this customer. The brief is NOT FK-linked to the
  // Need; the canonical correlation is `Need.sourceEventId == RiskBrief.inputsHash`,
  // but neither field is exposed by the current contract hooks (GetNeed doesn't
  // select sourceEventId; the briefs hook doesn't return inputsHash). So we use the
  // documented fallback: the most-recent brief for the customer (briefs[0]).
  const { data: riskData, isLoading: briefsLoading } = useRiskBriefsForCustomer(customerId);
  const { data: customerData } = useCustomer(customerId || '');
  const customer = customerData?.customer;
  const stakeholders = customerData?.stakeholders;
  const signals = customerData?.signals;

  const briefs = riskData?.briefs || [];
  const hasBrief = briefs.length > 0;

  // In embedded mode (inside Conversations), start compose open — the user is here
  // to triage and act; no need to hide it behind a button.
  const [composeOpen, setComposeOpen] = useState(!!embedded);

  const customerName = need.customer?.name || 'Customer';
  const severity = needSeverity(need.type);
  const header = playTitle(need.type, customerName);

  return (
    <div className={cn(!embedded && 'mx-auto max-w-6xl')}>
      {/* Breadcrumb — hidden in embedded (Conversations) mode */}
      {!embedded && (
        <Link
          to="/app/conversations"
          className="mb-8 inline-flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-charcoal-400 transition-colors hover:text-cream-200"
        >
          <ChevronLeft className="h-4 w-4" />
          <span>Back to Conversations</span>
        </Link>
      )}

      {/* Header */}
      <header className="mb-8">
        <div className="mb-4 flex items-center gap-4">
          <Pulse active={!need.snoozed_until} />
          <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-widest text-charcoal-500">
            <RefCode className="font-bold text-rust-500">
              {need.id.slice(0, 8).toUpperCase()}
            </RefCode>
            <span>//</span>
            <span className={cn('font-semibold', severityText[severity])}>PROACTIVE PLAY</span>
            <span>//</span>
            <Timestamp time={formatTime(need.updated_at)} />
          </div>

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={onSnooze}
              className="rounded p-2 text-charcoal-400 transition-colors hover:bg-charcoal-800 hover:text-cream-200"
              title="Snooze for 24h"
            >
              <Clock className="h-5 w-5" />
            </button>
            <button
              onClick={onResolve}
              className="rounded p-2 text-charcoal-400 transition-colors hover:bg-charcoal-800 hover:text-emerald-500"
              title="Mark resolved"
            >
              <Check className="h-5 w-5" />
            </button>
          </div>
        </div>

        <h1 className="font-serif text-3xl leading-tight text-cream-100">{header}</h1>
        <p className="mt-2 text-sm italic text-charcoal-400">
          A play is the pre-conversation state. Review the brief and the save play, then open compose
          to graduate it into a conversation.
        </p>
      </header>

      {/* Main grid — play body + context rail (right hidden when embedded) */}
      <div className={cn('grid grid-cols-1 gap-8', !embedded && 'lg:grid-cols-3')}>
        <div className={cn('space-y-6', !embedded && 'lg:col-span-2')}>
          {/* The brief + the save play. Reuse RiskSavePlayCard for visual parity
              with Customer Detail when a brief row exists. */}
          {briefsLoading && !hasBrief ? (
            <div className="h-48 animate-pulse rounded border border-charcoal-700 bg-charcoal-800" />
          ) : hasBrief ? (
            <RiskSavePlayCard
              briefs={briefs}
              daysToRenewal={customer?.days_to_renewal}
              healthLabel={customer?.relationship_health}
              healthScore={customer?.relationship_health_score}
              arrCents={customer?.arr_cents}
              lifecycle={customer?.lifecycle}
              stakeholders={stakeholders}
              signals={signals}
              onStartPlay={() => setComposeOpen(true)}
            />
          ) : (
            <BriefFallback need={need} />
          )}

          {/* Compose — the graduation entry point. Opens the existing draft surface.
              The send→graduate lifecycle (send creates the thread, flips status to a
              conversation) is Track-B data behavior; here we provide the affordance. */}
          {composeOpen ? (
            <div>
              <div className="mb-2 flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-widest text-rust-400">
                <PenLine className="h-3.5 w-3.5" />
                Compose · graduates this play into a conversation
              </div>
              <DraftPanel
                draft={(need.draft || null) as RawDraft | null}
                threadId={need.thread_id || ''}
                recipient={customerName}
                needId={need.id}
              />
            </div>
          ) : null}
        </div>

        {/* Right rail — omitted when embedded; Conversations.tsx renders PlayRailContent there */}
        {!embedded && <div className="sticky top-12 self-start space-y-4">
          <div className="rounded-md border border-border bg-surface">
            <ContextRail customerId={customerId} />
          </div>

          {/* Sidekick note — the agent's reasoning for surfacing this play. */}
          {(need.agent_reasoning || need.lede) && (
            <SidekickObserved>
              {need.agent_reasoning || need.lede}
            </SidekickObserved>
          )}

          {/* CTAs — Open compose graduates the play; secondary is Customer Detail. */}
          <div className="space-y-2">
            <button
              onClick={() => setComposeOpen(true)}
              className="flex w-full items-center justify-center gap-2 bg-rust-500 px-4 py-3 font-mono text-xs font-bold uppercase tracking-widest text-charcoal-900 transition-colors hover:bg-rust-400"
            >
              <PenLine className="h-4 w-4" />
              Open compose
            </button>
            {customerId && (
              <button
                onClick={() => navigate(`/app/customers/${customerId}`)}
                className="flex w-full items-center justify-center gap-2 border border-charcoal-600 px-4 py-2.5 font-mono text-[11px] uppercase tracking-widest text-charcoal-400 transition-colors hover:text-cream-200"
              >
                <MessageSquare className="h-3.5 w-3.5" />
                Open customer
              </button>
            )}
          </div>
        </div>}
      </div>
    </div>
  );
}

/**
 * Graceful brief when no RiskBrief row exists yet. Renders the need's own
 * one-liner + agent reasoning in the brief shape so the play reads clean, never
 * an empty thread or fabricated steps.
 */
function BriefFallback({ need }: { need: Need }) {
  return (
    <div className="rounded-md border border-charcoal-700 bg-charcoal-800 p-6">
      <h2 className="mb-4 font-serif text-2xl text-cream-100">{need.headline}</h2>

      {need.lede && (
        <div className="mb-4">
          <h4 className="mb-1 font-mono text-[10px] uppercase tracking-[0.2em] text-charcoal-400">
            The brief
          </h4>
          <p className="text-cream-200">{need.lede}</p>
        </div>
      )}

      {need.agent_reasoning && (
        <div className="border-l border-charcoal-600 pl-4">
          <h4 className="mb-1 font-mono text-[10px] uppercase tracking-[0.2em] text-charcoal-400">
            Why this surfaced
          </h4>
          <p className="text-sm leading-relaxed text-charcoal-300">{need.agent_reasoning}</p>
        </div>
      )}

      <p className="mt-6 text-sm italic text-charcoal-500">
        The save play hasn't been generated yet. Sidekick will fill in the ordered steps once it
        finishes investigating this account.
      </p>
    </div>
  );
}
