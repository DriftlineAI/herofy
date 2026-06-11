// Thread header — breadcrumbs, subject, channel + primary-need chip.

import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  channelTag,
  needSeverity,
  severityText,
  needTypeLabel,
  type Severity,
} from './conversationUtils';

interface ThreadHeaderProps {
  subject: string | null;
  customerName?: string | null;
  channel?: string | null;
  primaryNeedType?: string | null;
  className?: string;
}

export function ThreadHeader({
  subject,
  customerName,
  channel,
  primaryNeedType,
  className,
}: ThreadHeaderProps) {
  const sev: Severity = needSeverity(primaryNeedType);
  return (
    <div className={cn('border-b border-border pb-4', className)}>
      <nav className="mb-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-fg-400">
        <Link to="/app/conversations" className="hover:text-fg-200">
          Conversations
        </Link>
        {customerName && (
          <>
            <span>›</span>
            <span className="text-fg-300">{customerName}</span>
          </>
        )}
      </nav>
      <h2 className="font-serif text-2xl leading-tight text-fg-100">
        {subject || 'Untitled conversation'}
      </h2>
      <div className="mt-2 flex items-center gap-3">
        <span className="rounded-sm border border-border px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wider text-fg-300">
          {channelTag(channel)}
        </span>
        {primaryNeedType && (
          <span
            className={cn(
              'font-mono text-[10px] font-semibold uppercase tracking-wider',
              severityText[sev],
            )}
          >
            {needTypeLabel(primaryNeedType)}
          </span>
        )}
      </div>
    </div>
  );
}
