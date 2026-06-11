// ============================================================
// RENEWALS — shared types + pure display/derivation helpers
// Posture/plays/risk are stored in the DB (RenewalProfile/Play/RiskItem);
// these helpers only format and compute portfolio-level aggregates.
// ============================================================

import type { SignalState, StakeholderStatus } from './api';

export type RenewalPosture = 'expand' | 'hold' | 'defend';
export type RenewalPlayKind =
  | 're_anchor' | 'de_risk' | 're_seat'
  | 'upsell' | 'multi_year' | 'co_success' | 'early_close';
export type RiskLevel = 'low' | 'medium' | 'high';
export type GrowthDirection = 'up' | 'flat' | 'down';

export interface RenewalProfile {
  id: string;
  posture: RenewalPosture;
  posture_reason: string | null;
  narrative_lede: string | null;
  target_arr_cents: number | null;
  expansion_pipe_cents: number | null;
  renewal_type: string | null;
  auto_renew: boolean | null;
  term_note: string | null;
  last_price_change_note: string | null;
  posture_set_by: string | null;
  posture_derived_at: string | null;
}

export interface RenewalGoalVector {
  id: string;
  category: string;
  description: string;
  current_state: SignalState;
  progress: number | null;
  baseline_progress: number | null;
  target_progress: number | null;
  target_label: string | null;
  unlocks: string | null;          // "say it as" coaching line
  assessment_reason: string | null;
}

export interface RenewalGoal {
  id: string;
  text: string;
  is_primary: boolean;
  vectors: RenewalGoalVector[];
}

export interface RenewalStakeholder {
  id: string;
  name: string;
  role: string | null;
  status: StakeholderStatus;
  is_champion: boolean;
  sentiment_note: string | null;
  last_interaction_at: string | null;
  tone: SignalState;               // derived: renewalHealth, else from status/sentiment
  initials: string;
}

export interface RenewalPlay {
  id: string;
  kind: RenewalPlayKind;
  posture: RenewalPosture;
  title: string;
  description: string;
  basis: string | null;
  value_amount_cents: number | null;
  value_label: string | null;
  is_primary: boolean;
  sort_order: number;
}

export interface RenewalRiskItem {
  id: string;
  title: string;
  description: string;
  severity: RiskLevel;
  mitigation: string | null;
  sort_order: number;
}

// One row in the pipeline list.
export interface RenewalPipelineRow {
  id: string;
  name: string;
  slug: string;
  arr_cents: number | null;
  days_to_renewal: number | null;
  lifecycle: string;
  renewal_readiness: string | null;
  value_realization_text: string | null;
  client_signed_date: string | null;
  profile: RenewalProfile | null;
  goals: RenewalGoal[];
  signals: Array<{ kind: string; state: SignalState; sentence: string | null }>;
  champion_departed: boolean;
  // derived conveniences
  posture: RenewalPosture;
  growth: GrowthDirection;
}

// Full detail for the workspace screen.
export interface RenewalWorkspaceData {
  id: string;
  name: string;
  slug: string;
  one_liner: string | null;
  tier: string | null;
  arr_cents: number | null;
  days_to_renewal: number | null;
  lifecycle: string;
  renewal_readiness: string | null;
  value_realization_text: string | null;
  client_signed_date: string | null;
  relationship_health: string | null;
  relationship_health_score: number | null;
  profile: RenewalProfile | null;
  posture: RenewalPosture;
  goals: RenewalGoal[];
  stakeholders: RenewalStakeholder[];
  plays: RenewalPlay[];
  risk_items: RenewalRiskItem[];
  signals: Array<{ id: string; kind: string; state: SignalState; sentence: string | null; evidence_text: string | null }>;
}

export interface PortfolioStats {
  renewing_arr_cents: number;
  expansion_pipe_cents: number;
  at_risk_arr_cents: number;
  account_count: number;
  net_retention_pct: number | null;
  expand_count: number;
  hold_count: number;
  defend_count: number;
}

// ---- helpers -------------------------------------------------

/** Format ARR (cents) as $24K / $1.2M. */
export function formatARR(cents: number | string | null | undefined): string {
  if (cents == null || cents === '') return '—';
  const amount = Number(cents) / 100;
  if (!Number.isFinite(amount)) return '—';
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
  return `$${amount.toFixed(0)}`;
}

/** Growth direction from current vs target ARR. */
export function deriveGrowth(arrCents: number | null, targetArrCents: number | null, posture: RenewalPosture): GrowthDirection {
  if (posture === 'defend') return 'down';
  if (targetArrCents != null && arrCents != null) {
    if (targetArrCents > arrCents) return 'up';
    if (targetArrCents < arrCents) return 'down';
  }
  return 'flat';
}

/** Two-letter initials for an avatar. */
export function initialsOf(name: string): string {
  const parts = (name || '').trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return (name || '?').slice(0, 2).toUpperCase();
}

/** Stakeholder display tone: explicit renewalHealth wins, else derive from status/sentiment. */
export function stakeholderTone(args: {
  renewalHealth?: SignalState | null;
  status: StakeholderStatus;
  sentimentNote?: string | null;
}): SignalState {
  if (args.renewalHealth) return args.renewalHealth;
  if (args.status === 'departed') return 'risk';
  const note = (args.sentimentNote || '').toLowerCase();
  if (/churn|risk|negative|cold|silent|mandate|consolidat|cpq|blocker|concern/.test(note)) return 'warn';
  return 'ok';
}

/** Convert a date string (or null) into a short renewal date label given days-to-renewal. */
export function renewalDateLabel(daysToRenewal: number | null, now: Date = new Date()): string {
  if (daysToRenewal == null) return '—';
  const d = new Date(now.getTime() + daysToRenewal * 24 * 60 * 60 * 1000);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
}

/** Portfolio stat strip from the pipeline rows. */
export function computePortfolioStats(rows: RenewalPipelineRow[]): PortfolioStats {
  let renewing = 0, expansion = 0, atRisk = 0;
  let expand = 0, hold = 0, defend = 0;
  for (const r of rows) {
    const arr = r.arr_cents || 0;
    renewing += arr;
    if (r.posture === 'expand') expand++;
    else if (r.posture === 'defend') { defend++; atRisk += arr; }
    else hold++;
    const pipe = r.profile?.expansion_pipe_cents
      ?? (r.profile?.target_arr_cents && r.profile.target_arr_cents > arr ? r.profile.target_arr_cents - arr : 0);
    expansion += pipe || 0;
  }
  const net_retention_pct = renewing > 0 ? Math.round(((renewing + expansion - atRisk) / renewing) * 100) : null;
  return {
    renewing_arr_cents: renewing,
    expansion_pipe_cents: expansion,
    at_risk_arr_cents: atRisk,
    account_count: rows.length,
    net_retention_pct,
    expand_count: expand,
    hold_count: hold,
    defend_count: defend,
  };
}

export const PLAY_KIND_LABEL: Record<RenewalPlayKind, string> = {
  re_anchor: 'RE-ANCHOR',
  de_risk: 'DE-RISK',
  re_seat: 'RE-SEAT',
  upsell: 'UPSELL',
  multi_year: 'MULTI-YEAR',
  co_success: 'CO-SUCCESS',
  early_close: 'EARLY CLOSE',
};

export const POSTURE_LABEL: Record<RenewalPosture, string> = {
  expand: 'EXPAND',
  hold: 'HOLD',
  defend: 'DEFEND',
};
