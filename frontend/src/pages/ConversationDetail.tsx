import { useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  useThread,
  useThreadMessages,
  useNeed,
  useThreadDraft,
} from '@/lib/dataconnect-hooks';
import { ThreadHeader } from '@/components/conversation/ThreadHeader';
import { ThreadListRail } from '@/components/conversation/ThreadListRail';
import { ContextRail } from '@/components/conversation/ContextRail';
import { MessageList } from '@/components/conversation/MessageList';
import { DraftPanel } from '@/components/conversation/DraftPanel';
import { HuddlePanel } from '@/components/conversation/HuddlePanel';
import { ThreadNeeds } from '@/components/conversation/ThreadNeeds';
import type { RawDraft } from '@/components/conversation/DraftPanel';
import { Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';

type ComposeTab = 'reply' | 'huddle';

export default function ConversationDetail() {
  const { threadId } = useParams<{ threadId: string }>();
  const tid = threadId || '';

  const { data: threadData, isLoading } = useThread(tid);
  const thread = threadData?.thread;

  const { data: messagesData, refetch: refetchMessages } = useThreadMessages(tid);
  const { data: needData, refetch: refetchNeed } = useNeed(thread?.need_id || '');
  const need = needData?.need;
  const { data: draftData, refetch: refetchDraft } = useThreadDraft(tid);

  // After a draft send/reject/regenerate: the message timeline, the compose draft, and the need
  // (its draft fallback + status) all change — refetch all three from the server (DataConnect
  // reads PREFER_CACHE, so a plain refetch would keep serving the pre-send cache).
  const handleComposeChanged = useCallback(() => {
    refetchDraft();
    refetchMessages();
    refetchNeed();
  }, [refetchDraft, refetchMessages, refetchNeed]);

  const [tab, setTab] = useState<ComposeTab>('reply');
  const [pinnedInteractionId, setPinnedInteractionId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center py-16">
        <div className="flex items-center gap-2 text-fg-400">
          <Pulse continuous />
          <span className="font-mono text-xs uppercase tracking-widest">Loading conversation…</span>
        </div>
      </div>
    );
  }

  if (!thread || !tid) {
    return (
      <div className="mx-auto max-w-md px-6 py-16 text-center">
        <h2 className="font-serif text-2xl text-fg-100">Conversation not found</h2>
        <p className="mt-2 text-sm text-fg-400">
          This thread may have been resolved or removed.
        </p>
      </div>
    );
  }

  const customerId = thread.customer?.id || null;
  const messages = messagesData?.messages || [];
  const resolved = thread.status === 'resolved';

  // Prefer the thread-anchored draft; fall back to the surfaced need's draft.
  // Both are contract draft sources with slightly different raw shapes; DraftPanel
  // normalizes them (see RawDraft).
  const composeDraft = (draftData?.draft || need?.draft || null) as RawDraft | null;
  const recipient = thread.customer?.name || null;

  function handlePinHuddle(interactionId: string) {
    setPinnedInteractionId(interactionId);
    setTab('huddle');
  }

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-[18rem_1fr_20rem]">
      {/* Left — focused inbox rail */}
      <div className="hidden border-r border-border lg:flex lg:flex-col">
        <ThreadListRail activeThreadId={tid} />
      </div>

      {/* Center — thread + compose */}
      <div className="flex min-w-0 flex-col overflow-y-auto px-6 py-5">
        <ThreadHeader
          subject={thread.subject}
          customerName={thread.customer?.name}
          channel={thread.channel}
          primaryNeedType={need?.type}
        />

        {/* All needs on this thread (1:N fan-out) */}
        <ThreadNeeds threadId={tid} className="mt-4" />

        {resolved && (
          <div className="mt-4 flex items-center gap-2 rounded-md border border-border bg-surface px-4 py-2.5">
            <span className="h-1.5 w-1.5 rounded-full bg-signal-ok" />
            <span className="font-mono text-[10px] font-semibold tracking-wider text-signal-ok">
              RESOLVED
            </span>
            <span className="text-xs text-fg-400">This conversation is closed.</span>
          </div>
        )}

        <div className="mt-5 flex-1">
          <MessageList messages={messages} onPinHuddle={handlePinHuddle} />
        </div>

        {/* Compose: reply (draft) / huddle tabs */}
        {!resolved && (
          <div className="mt-6 border-t border-border pt-4">
            <div className="mb-3 flex gap-1">
              <TabButton active={tab === 'reply'} onClick={() => setTab('reply')}>
                Reply
              </TabButton>
              <TabButton active={tab === 'huddle'} onClick={() => setTab('huddle')}>
                Internal huddle
              </TabButton>
            </div>

            {tab === 'reply' ? (
              <DraftPanel
                draft={composeDraft}
                threadId={tid}
                recipient={recipient}
                needId={need?.id}
                onChanged={handleComposeChanged}
              />
            ) : (
              <HuddlePanel
                threadId={tid}
                customerId={customerId}
                anchorInteractionId={pinnedInteractionId}
              />
            )}
          </div>
        )}
      </div>

      {/* Right — context rail */}
      <div className="hidden border-l border-border lg:block lg:overflow-y-auto">
        <ContextRail customerId={customerId} />
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-sm px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors',
        active ? 'bg-surface-2 text-rust-400' : 'text-fg-400 hover:bg-surface-2 hover:text-fg-200',
      )}
    >
      {children}
    </button>
  );
}
