import { Link } from 'react-router-dom';
import { AlertTriangle, Mail, MessageSquare, Clock } from 'lucide-react';
import { RefCode, Timestamp } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import type { OrphanThread } from '@/lib/dataconnect-hooks';

export interface OrphanThreadCardProps {
  thread: OrphanThread;
  key?: string;
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return '1d ago';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function ChannelIcon({ channel }: { channel: string }) {
  switch (channel) {
    case 'slack':
      return <MessageSquare className="w-3 h-3" />;
    case 'email':
    default:
      return <Mail className="w-3 h-3" />;
  }
}

export function OrphanThreadCard({ thread }: OrphanThreadCardProps) {
  const snippet = thread.latest_interaction?.summary_ai || thread.subject || '';

  return (
    <Link
      to={`/app/conversations/${thread.id}`}
      className="relative bg-charcoal-800 border-l-4 border-l-amber-500/50 p-4 px-6 flex flex-col md:flex-row gap-4 items-start md:items-center hover:bg-charcoal-700/50 transition-colors cursor-pointer block group"
    >
      {/* Warning indicator */}
      <div className="absolute -top-2 left-4 flex items-center gap-1.5 bg-amber-500/20 text-amber-400 px-2 py-0.5 text-[9px] font-mono uppercase tracking-widest">
        <AlertTriangle className="w-2.5 h-2.5" />
        <span>No Need Attached</span>
      </div>

      <div className="w-full md:w-1/5 flex gap-4 items-center pt-2">
        <span className="font-serif text-lg text-cream-200">{thread.customer_name}</span>
      </div>

      <div className="flex-1 truncate text-sm text-cream-300">
        <span className="font-medium mr-2 flex items-center gap-2">
          <ChannelIcon channel={thread.channel} />
          {thread.subject || 'No subject'}
        </span>
        {snippet && (
          <span className="text-charcoal-400 italic">"{snippet}"</span>
        )}
      </div>

      <div className="flex items-center gap-4 w-full md:w-auto justify-between md:justify-end">
        <RefCode className="text-charcoal-500 text-[9px]">{thread.id.slice(0, 8)}</RefCode>
        <div className={cn(
          'flex items-center gap-1.5 px-2 py-0.5 text-xs',
          thread.status === 'resolved' ? 'bg-emerald-900/30 text-emerald-400' : 'bg-amber-900/30 text-amber-400'
        )}>
          {thread.status === 'resolved' ? (
            <>
              <span className="hidden sm:inline">Resolved</span>
            </>
          ) : (
            <>
              <Clock className="w-3 h-3" />
              <span className="hidden sm:inline">Open</span>
            </>
          )}
        </div>
        <Timestamp time={formatTime(thread.updated_at)} />
      </div>
    </Link>
  );
}

export default OrphanThreadCard;
