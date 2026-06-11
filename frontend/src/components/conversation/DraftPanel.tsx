// Compose / AI draft surface. Renders the Sidekick draft (from useThreadDraft or
// need.draft) with citations as "vector preview" highlights when present, plain
// body when empty. Wires accept / reject / request-draft actions. Mock-free.

import { useState } from 'react';
import {
  useSendDraft,
  useRejectDraft,
  useRequestDraft,
} from '@/lib/dataconnect-hooks';
import { Pulse, Timestamp } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { VectorPreview, normalizeCitations } from './VectorPreview';
import { formatTime } from './conversationUtils';

// The compose draft can arrive from two contract sources with slightly different
// raw shapes: `useThreadDraft().draft` (raw DraftResponse, camelCase) or
// `need.draft` (snake_case adapter). We accept a permissive shape and read both.
export interface RawDraft {
  id: string;
  subject?: string | null;
  body: string;
  citations?: unknown;
  edited_body?: string | null;
  editedBody?: string | null;
  status?: string | null;
  generated_at?: string | null;
  generatedAt?: string | null;
}

interface NormalizedDraft {
  id: string;
  subject: string | null;
  body: string;
  editedBody: string | null;
  citations: unknown;
  generatedAt: string | null;
}

function normalizeDraft(d: RawDraft | null): NormalizedDraft | null {
  if (!d) return null;
  return {
    id: d.id,
    subject: d.subject ?? null,
    body: d.body,
    editedBody: d.edited_body ?? d.editedBody ?? null,
    citations: d.citations ?? null,
    generatedAt: d.generated_at ?? d.generatedAt ?? null,
  };
}

interface DraftPanelProps {
  draft: RawDraft | null;
  threadId: string;
  /** Recipient line for the compose header (from thread/customer). */
  recipient?: string | null;
  /**
   * The need this reply addresses. When set, a successful send transitions it to
   * `awaiting_customer` (standard "we replied, ball's in their court" behavior).
   */
  needId?: string | null;
  onChanged?: () => void;
  className?: string;
}

const btnBase =
  'inline-flex items-center gap-1.5 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest transition-colors disabled:opacity-50';

export function DraftPanel({
  draft: rawDraft,
  threadId,
  recipient,
  needId,
  onChanged,
  className,
}: DraftPanelProps) {
  const sendDraft = useSendDraft();
  const rejectDraft = useRejectDraft();
  const requestDraft = useRequestDraft();

  // Freshly-generated draft returned by the generate POST — rendered immediately because
  // refetch-after-write doesn't reliably surface DataConnect writes. The real `draft` prop takes
  // over once it loads (page reload / next fetch).
  const [optimistic, setOptimistic] = useState<RawDraft | null>(null);
  const draft = normalizeDraft(rawDraft) ?? normalizeDraft(optimistic);
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(draft?.editedBody || draft?.body || '');
  const [busy, setBusy] = useState(false);

  async function handleRequest() {
    setBusy(true);
    try {
      const res = await requestDraft.mutateAsync({ threadId });
      if (res?.draft_id && res?.draft_body) {
        setOptimistic({
          id: res.draft_id,
          body: res.draft_body,
          status: 'pending_review',
          generatedAt: new Date().toISOString(),
        });
      }
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  async function handleAccept() {
    if (!draft) return;
    setBusy(true);
    try {
      // Backend send action: posts the email as a sent message on the thread, marks the draft
      // sent, moves the Need to awaiting_customer, and auto-completes the matching save-play step.
      // (Simulated — no real email yet.) Drops the optimistic draft so the compose panel clears.
      await sendDraft.mutateAsync({ threadId, editedContent: editing ? body : undefined });
      setOptimistic(null);
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    if (!draft) return;
    setBusy(true);
    try {
      await rejectDraft.mutateAsync({ threadId, draftId: draft.id });
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  // Empty state — no draft yet. Offer to request one.
  if (!draft) {
    return (
      <div className={cn('rounded-md border border-border bg-surface p-5', className)}>
        <div className="flex items-center gap-2">
          <Pulse continuous />
          <span className="font-mono text-[10px] font-semibold tracking-widest text-fg-400">
            COMPOSE
          </span>
        </div>
        {busy ? (
          <p className="mt-2 flex items-center gap-2 text-sm text-fg-300">
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            Sidekick is drafting — grounding in this account's context…
          </p>
        ) : (
          <>
            <p className="mt-2 text-sm text-fg-300">
              No Sidekick draft yet. Generate one grounded in this account's context, or reply manually.
            </p>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={handleRequest}
                className={cn(btnBase, 'bg-accent text-page hover:bg-accent-hover')}
              >
                Ask Sidekick to draft
              </button>
            </div>
          </>
        )}
      </div>
    );
  }

  const hasCitations = normalizeCitations(draft.citations).length > 0;
  const effectiveBody = draft.editedBody || draft.body;

  return (
    <div className={cn('overflow-hidden rounded-md border border-border bg-surface', className)}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-2 px-5 py-3">
        <Pulse continuous />
        <span className="font-mono text-[10px] font-semibold tracking-widest text-rust-500">
          SIDEKICK DRAFTED · YOUR REVIEW
        </span>
        {hasCitations && (
          <span className="rounded-sm border border-rust-700 px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider text-rust-400">
            VECTOR-GROUNDED
          </span>
        )}
        {draft.generatedAt && (
          <span className="ml-auto">
            <Timestamp time={`DRAFTED ${formatTime(draft.generatedAt)}`} />
          </span>
        )}
      </div>

      <div className="px-5 py-4">
        {recipient && (
          <div className="mb-3 flex items-baseline gap-2 border-b border-border pb-2">
            <span className="font-mono text-[10px] tracking-wider text-fg-400">TO</span>
            <span className="text-sm text-fg-200">{recipient}</span>
          </div>
        )}
        {draft.subject && <h4 className="mb-3 font-serif text-lg text-fg-100">{draft.subject}</h4>}

        {editing ? (
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={12}
            className="w-full resize-y rounded-md border border-border bg-bg px-3 py-2 text-sm leading-relaxed text-fg-100 focus:border-rust-500 focus:outline-none"
          />
        ) : (
          <VectorPreview body={effectiveBody} citations={draft.citations} />
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-3">
        <button
          type="button"
          disabled={busy}
          onClick={handleAccept}
          className={cn(btnBase, 'bg-accent text-page hover:bg-accent-hover')}
        >
          Approve &amp; send
        </button>
        {editing ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => setEditing(false)}
            className={cn(btnBase, 'border border-border text-fg-200 hover:bg-surface-2')}
          >
            Done editing
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setBody(effectiveBody);
              setEditing(true);
            }}
            className={cn(btnBase, 'border border-border text-fg-200 hover:bg-surface-2')}
          >
            Edit
          </button>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={handleRequest}
          className={cn(btnBase, 'border border-border text-fg-200 hover:bg-surface-2')}
        >
          Regenerate
        </button>
        <div className="ml-auto" />
        <button
          type="button"
          disabled={busy}
          onClick={handleReject}
          className={cn(btnBase, 'text-fg-400 hover:text-fg-200')}
        >
          Discard
        </button>
      </div>
    </div>
  );
}
