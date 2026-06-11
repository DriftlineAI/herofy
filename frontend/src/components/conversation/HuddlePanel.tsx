// Internal huddle — collaboration anchored to a message OR the whole conversation.
// Renders user + @sidekick (agent) messages, supports @mentions, and create/post/
// resolve via the contract hooks. Mock-free: empty hooks => clean empty state.

import { useState } from 'react';
import {
  useThreadHuddles,
  useCreateHuddle,
  usePostHuddleMessage,
  useResolveHuddle,
} from '@/lib/dataconnect-hooks';
import { useWorkspace } from '@/lib/workspace';
import { Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { Avatar, renderWithMentions, extractMentions } from './conversationUtils';

interface HuddleMessage {
  id: string;
  author_kind: 'user' | 'agent';
  author_name: string | null;
  body: string;
  mentions: string[];
  created_at: string;
}

interface Huddle {
  id: string;
  title: string | null;
  status: string;
  anchor_interaction_id: string | null;
  messages: HuddleMessage[];
}

interface HuddlePanelProps {
  threadId: string;
  customerId: string | null;
  /** When set, a created huddle is pinned to this message; else conversation-level. */
  anchorInteractionId?: string | null;
  className?: string;
}

export function HuddlePanel({
  threadId,
  customerId,
  anchorInteractionId,
  className,
}: HuddlePanelProps) {
  const { workspaceId } = useWorkspace();
  const { data, isLoading, refetch } = useThreadHuddles(threadId);
  const createHuddle = useCreateHuddle();
  const postMessage = usePostHuddleMessage();
  const resolveHuddle = useResolveHuddle();

  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const list: Huddle[] = (data?.huddles as Huddle[] | undefined) || [];

  async function handlePost(huddleId: string) {
    if (!draft.trim()) return;
    setBusy(true);
    try {
      await postMessage.mutateAsync({
        huddleId,
        body: draft.trim(),
        authorKind: 'user',
        mentions: extractMentions(draft),
      });
      setDraft('');
      await refetch();
    } finally {
      setBusy(false);
    }
  }

  async function handleStartHuddle() {
    if (!customerId || !workspaceId) return;
    setBusy(true);
    try {
      await createHuddle.mutateAsync({
        workspaceId,
        customerId,
        threadId,
        anchorInteractionId: anchorInteractionId ?? undefined,
        title: anchorInteractionId ? 'Pinned huddle' : 'Conversation huddle',
      });
      await refetch();
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve(huddleId: string) {
    setBusy(true);
    try {
      await resolveHuddle.mutateAsync(huddleId);
      await refetch();
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return (
      <div className={cn('rounded-md border border-border bg-surface p-4', className)}>
        <div className="h-4 w-40 animate-pulse rounded bg-surface-2" />
        <div className="mt-3 h-12 w-full animate-pulse rounded bg-surface-2" />
      </div>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {list.length === 0 ? (
        <div className="rounded-md border border-dashed border-border bg-surface p-4 text-center">
          <p className="text-sm text-fg-300">No internal huddle on this thread yet.</p>
          <p className="mt-1 text-xs text-fg-400">
            Loop in your team or ask <span className="font-mono text-rust-400">@sidekick</span> —
            visible only to you, not the customer.
          </p>
          <button
            type="button"
            disabled={busy || !customerId || !workspaceId}
            onClick={handleStartHuddle}
            className="mt-3 inline-flex items-center gap-2 border border-border px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-fg-200 transition-colors hover:bg-surface-2 disabled:opacity-50"
          >
            Start a huddle
          </button>
        </div>
      ) : (
        list.map((huddle) => (
          <HuddleCard
            key={huddle.id}
            huddle={huddle}
            busy={busy}
            draft={draft}
            onDraftChange={setDraft}
            onPost={() => handlePost(huddle.id)}
            onResolve={() => handleResolve(huddle.id)}
          />
        ))
      )}
    </div>
  );
}

function HuddleCard({
  huddle,
  busy,
  draft,
  onDraftChange,
  onPost,
  onResolve,
}: {
  huddle: Huddle;
  busy: boolean;
  draft: string;
  onDraftChange: (v: string) => void;
  onPost: () => void;
  onResolve: () => void;
}) {
  const resolved = huddle.status === 'resolved';
  return (
    <div className="overflow-hidden rounded-md border border-border bg-surface-2">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="font-mono text-[10px] font-semibold tracking-widest text-rust-500">
          INTERNAL HUDDLE
        </span>
        <span className="text-[10px] text-fg-400">· NOT VISIBLE TO CUSTOMER</span>
        <span className="ml-auto font-mono text-[10px] text-fg-400">
          {huddle.anchor_interaction_id ? 'PINNED TO MESSAGE' : 'CONVERSATION-LEVEL'}
          {' · '}
          {huddle.messages.length} {huddle.messages.length === 1 ? 'NOTE' : 'NOTES'}
        </span>
        {resolved ? (
          <span className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider text-signal-ok">
            RESOLVED
          </span>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={onResolve}
            className="rounded-sm border border-border px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider text-fg-300 hover:bg-surface disabled:opacity-50"
          >
            RESOLVE
          </button>
        )}
      </div>

      <div className="space-y-3 px-4 py-3">
        {huddle.messages.length === 0 ? (
          <p className="text-xs text-fg-400">No notes yet.</p>
        ) : (
          huddle.messages.map((m) => (
            <div key={m.id} className="flex gap-3">
              <Avatar
                name={m.author_name}
                agent={m.author_kind === 'agent'}
                size="sm"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-medium text-fg-100">
                    {m.author_kind === 'agent' ? 'Sidekick' : m.author_name || 'Teammate'}
                  </span>
                  <span
                    className={cn(
                      'font-mono text-[9px] uppercase tracking-wider',
                      m.author_kind === 'agent' ? 'text-rust-400' : 'text-fg-400',
                    )}
                  >
                    {m.author_kind === 'agent' ? 'AI' : 'TEAM'}
                  </span>
                </div>
                <p className="mt-0.5 whitespace-pre-wrap text-sm leading-relaxed text-fg-200">
                  {renderWithMentions(m.body)}
                </p>
              </div>
            </div>
          ))
        )}
      </div>

      {!resolved && (
        <div className="border-t border-border px-4 py-3">
          <textarea
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            placeholder="Add a note… use @name or @sidekick"
            rows={2}
            className="w-full resize-none rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg-100 placeholder:text-fg-400 focus:border-rust-500 focus:outline-none"
          />
          <div className="mt-2 flex items-center gap-2">
            <Pulse continuous />
            <span className="text-[11px] text-fg-400">
              Mention <span className="font-mono text-rust-400">@sidekick</span> to ask the agent.
            </span>
            <button
              type="button"
              disabled={busy || !draft.trim()}
              onClick={onPost}
              className="ml-auto inline-flex items-center gap-2 bg-accent px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-page transition-colors hover:bg-accent-hover disabled:opacity-50"
            >
              Post note
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
