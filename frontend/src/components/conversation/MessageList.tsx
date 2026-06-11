// Thread messages (from useThreadMessages). Customer vs. us styling, with a
// per-message "huddle here" affordance so a huddle can be pinned to a message.

import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth';
import { Avatar, formatTime } from './conversationUtils';

export interface Message {
  id: string;
  direction: string | null;
  channel: string | null;
  sender_name: string | null;
  sender_email: string | null;
  body: string;
  created_at: string;
}

interface MessageListProps {
  messages: Message[];
  onPinHuddle?: (interactionId: string) => void;
  className?: string;
}

function isOutbound(direction: string | null): boolean {
  const d = (direction || '').toLowerCase();
  return d === 'outbound' || d === 'out' || d === 'sent' || d === 'us';
}

/** Parse "Company — Person" into { name, company }. Returns raw string as name if no separator. */
function parseSender(raw: string | null): { name: string; company: string | null } {
  if (!raw) return { name: 'Customer', company: null };
  const m = raw.match(/ [—–] /);
  if (m?.index !== undefined) {
    return {
      company: raw.slice(0, m.index).trim(),
      name: raw.slice(m.index + m[0].length).trim(),
    };
  }
  return { name: raw, company: null };
}

export function MessageList({ messages, onPinHuddle, className }: MessageListProps) {
  const { user } = useAuth();
  const currentUserName = user?.displayName || user?.email?.split('@')[0] || 'You';

  if (messages.length === 0) {
    return (
      <div className={cn('rounded-md border border-dashed border-border bg-surface p-6 text-center', className)}>
        <p className="text-sm text-fg-300">No messages in this thread yet.</p>
      </div>
    );
  }

  return (
    <div className={cn('space-y-5', className)}>
      {messages.map((m) => {
        // 'internal' = a Sidekick/agent note (gold SK avatar); 'us' = our outbound reply;
        // everything else = the customer. Internal + outbound both render on the team side.
        const internal = (m.direction || '').toLowerCase() === 'internal';
        const out = isOutbound(m.direction);
        const teamSide = internal || out;
        const { name: senderName, company } = internal
          ? { name: m.sender_name || 'Sidekick', company: null }
          : out
          ? { name: currentUserName, company: null }
          : parseSender(m.sender_name);
        return (
          <div key={m.id} className="group flex gap-3">
            <Avatar
              name={internal ? (m.sender_name || 'Sidekick') : out ? currentUserName : m.sender_name}
              email={teamSide ? undefined : m.sender_email}
              size="md"
              variant={teamSide ? 'internal' : 'customer'}
              agent={internal}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-medium text-fg-100">{senderName}</span>
                {company && (
                  <span className="font-mono text-[10px] uppercase tracking-wider text-accent">
                    {company}
                  </span>
                )}
                <span className="ml-auto font-mono text-[10px] text-fg-400">
                  {formatTime(m.created_at)}
                </span>
                {onPinHuddle && (
                  <button
                    type="button"
                    onClick={() => onPinHuddle(m.id)}
                    className="font-mono text-[9px] uppercase tracking-wider text-fg-400 opacity-0 transition-opacity hover:text-rust-400 group-hover:opacity-100"
                  >
                    + huddle
                  </button>
                )}
              </div>
              <div
                className={cn(
                  'mt-1 whitespace-pre-wrap rounded-r-md border-l-2 px-4 py-3 text-sm leading-relaxed',
                  out
                    ? 'border-accent bg-surface-2 text-fg-100'
                    : 'border-sky-500 bg-surface text-fg-200',
                )}
              >
                {m.body}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
