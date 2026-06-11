import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { useThread, useThreadMessages, useNeed, useThreadDraft } from '@/lib/dataconnect-hooks';
import { ThreadHeader } from '@/components/conversation/ThreadHeader';
import { ContextRail } from '@/components/conversation/ContextRail';
import { MessageList } from '@/components/conversation/MessageList';
import { DraftPanel } from '@/components/conversation/DraftPanel';
import { HuddlePanel } from '@/components/conversation/HuddlePanel';
import { ThreadNeeds } from '@/components/conversation/ThreadNeeds';
import type { RawDraft } from '@/components/conversation/DraftPanel';
import { BackBar } from '@/components/mobile/mobileShared';
import { cn } from '@/lib/utils';

type ComposeTab = 'reply' | 'huddle';

// Full-screen thread: the desktop right-rail context (ContextRail) is folded into
// a collapsible "Customer context" section at the top instead of a third column.
export default function MobileConversationDetail() {
  const { threadId } = useParams<{ threadId: string }>();
  const tid = threadId || '';

  const { data: threadData, isLoading } = useThread(tid);
  const thread = threadData?.thread;
  const { data: messagesData } = useThreadMessages(tid);
  const { data: needData } = useNeed(thread?.need_id || '');
  const need = needData?.need;
  const { data: draftData, refetch: refetchDraft } = useThreadDraft(tid);

  const [tab, setTab] = useState<ComposeTab>('reply');
  const [pinnedInteractionId, setPinnedInteractionId] = useState<string | null>(null);
  const [contextOpen, setContextOpen] = useState(false);

  if (!isLoading && (!thread || !tid)) {
    return (
      <div>
        <BackBar title="Conversation" fallback="/m/conversations" />
        <div className="px-6 py-16 text-center">
          <h2 className="font-display text-2xl text-fg-100">Conversation not found</h2>
          <p className="mt-2 text-sm text-fg-400">This thread may have been resolved or removed.</p>
        </div>
      </div>
    );
  }

  const customerId = thread?.customer?.id || null;
  const messages = messagesData?.messages || [];
  const resolved = thread?.status === 'resolved';
  const composeDraft = (draftData?.draft || need?.draft || null) as RawDraft | null;
  const recipient = thread?.customer?.name || null;

  return (
    <div>
      <BackBar
        title={thread?.customer?.name || 'Conversation'}
        subtitle={thread?.subject || undefined}
        fallback="/m/conversations"
      />

      {/* Folded context (was the desktop right rail) */}
      {customerId && (
        <div className="border-b border-border">
          <button
            onClick={() => setContextOpen((v) => !v)}
            className="flex w-full items-center gap-2 px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400"
          >
            <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', !contextOpen && '-rotate-90')} />
            Customer context
          </button>
          {contextOpen && (
            <div className="border-t border-border">
              <ContextRail customerId={customerId} />
            </div>
          )}
        </div>
      )}

      <div className="px-4 py-4">
        <ThreadHeader
          subject={thread?.subject ?? null}
          customerName={thread?.customer?.name}
          channel={thread?.channel}
          primaryNeedType={need?.type}
        />

        <ThreadNeeds threadId={tid} className="mt-4" />

        {resolved && (
          <div className="mt-4 flex items-center gap-2 rounded-md border border-border bg-surface px-4 py-2.5">
            <span className="h-1.5 w-1.5 rounded-full bg-signal-ok" />
            <span className="font-mono text-[10px] font-semibold tracking-wider text-signal-ok">RESOLVED</span>
            <span className="text-xs text-fg-400">This conversation is closed.</span>
          </div>
        )}

        <div className="mt-5">
          <MessageList
            messages={messages}
            onPinHuddle={(id) => {
              setPinnedInteractionId(id);
              setTab('huddle');
            }}
          />
        </div>

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
                onChanged={refetchDraft}
              />
            ) : (
              <HuddlePanel threadId={tid} customerId={customerId} anchorInteractionId={pinnedInteractionId} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-sm px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors',
        active ? 'bg-surface-2 text-rust-400' : 'text-fg-400',
      )}
    >
      {children}
    </button>
  );
}
