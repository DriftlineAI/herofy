import React, { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Mail,
  MessageSquare,
  Video,
  MonitorSmartphone,
  MessageCircle,
  StickyNote,
  Phone,
  Paperclip,
  Download,
  FileText,
  Image as ImageIcon,
} from 'lucide-react';
import { Timestamp } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import type { ThreadMessage, InteractionChannel, Attachment } from '@/lib/api';

interface ConversationThreadProps {
  messages: ThreadMessage[];
  isLoading?: boolean;
}

function getChannelIcon(channel: InteractionChannel) {
  const icons: Record<InteractionChannel, React.ReactNode> = {
    email: <Mail className="w-3.5 h-3.5" />,
    slack: <MessageSquare className="w-3.5 h-3.5" />,
    meeting: <Video className="w-3.5 h-3.5" />,
    in_app: <MonitorSmartphone className="w-3.5 h-3.5" />,
    sms_screenshot: <MessageCircle className="w-3.5 h-3.5" />,
    note: <StickyNote className="w-3.5 h-3.5" />,
    phone: <Phone className="w-3.5 h-3.5" />,
  };
  return icons[channel] || <Mail className="w-3.5 h-3.5" />;
}

function getChannelLabel(channel: InteractionChannel): string {
  const labels: Record<InteractionChannel, string> = {
    email: 'Email',
    slack: 'Slack',
    meeting: 'Meeting',
    in_app: 'In-App',
    sms_screenshot: 'SMS',
    note: 'Note',
    phone: 'Phone',
  };
  return labels[channel] || channel;
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  } else if (diffDays === 1) {
    return `Yesterday ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;
  } else if (diffDays < 7) {
    return date.toLocaleDateString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', hour12: true });
  } else {
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true });
  }
}

function getAttachmentIcon(mimeType: string) {
  if (mimeType.startsWith('image/')) {
    return <ImageIcon className="w-4 h-4" />;
  }
  return <FileText className="w-4 h-4" />;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function AttachmentPreview({ attachment }: { attachment: Attachment }) {
  const isImage = attachment.mime_type.startsWith('image/');

  return (
    <a
      href={attachment.url}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "flex items-center gap-3 p-2 rounded border border-charcoal-700 hover:border-charcoal-600 transition-colors",
        "bg-charcoal-800/50 group"
      )}
    >
      {isImage ? (
        <div className="w-12 h-12 rounded overflow-hidden bg-charcoal-700 flex-shrink-0">
          <img
            src={attachment.url}
            alt={attachment.filename}
            className="w-full h-full object-cover"
          />
        </div>
      ) : (
        <div className="w-12 h-12 rounded bg-charcoal-700 flex items-center justify-center flex-shrink-0">
          {getAttachmentIcon(attachment.mime_type)}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-cream-200 truncate group-hover:text-cream-100">
          {attachment.filename}
        </p>
        <p className="text-xs text-charcoal-400 font-mono">
          {formatFileSize(attachment.size_bytes)}
        </p>
      </div>
      <Download className="w-4 h-4 text-charcoal-500 group-hover:text-cream-300 flex-shrink-0" />
    </a>
  );
}

function MessageBubble({ message }: { message: ThreadMessage }) {
  const isCustomer = message.direction === 'customer';
  const isInternal = message.direction === 'internal';
  const isUs = message.direction === 'us';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "group relative",
        isCustomer && "mr-12 sm:mr-24",
        isUs && "ml-12 sm:ml-24",
        isInternal && "mx-0"
      )}
    >
      {/* Internal Note Banner */}
      {isInternal && (
        <div className="flex items-center gap-2 mb-2">
          <div className="h-px flex-1 border-t border-dashed border-rust-500/30" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-rust-400 bg-charcoal-900 px-2">
            Internal Note
          </span>
          <div className="h-px flex-1 border-t border-dashed border-rust-500/30" />
        </div>
      )}

      <div
        className={cn(
          "rounded-none p-4",
          isCustomer && "bg-charcoal-800",
          isUs && "bg-charcoal-900 border-l-2 border-l-rust-500/30",
          isInternal && "bg-rust-900/20 border border-dashed border-rust-500/30"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-4 mb-2">
          <div className="flex items-center gap-2">
            <span className={cn(
              "font-medium text-sm",
              isCustomer && "text-cream-100",
              isUs && "text-cream-200",
              isInternal && "text-rust-300"
            )}>
              {message.sender_name}
            </span>

            {/* Channel Badge */}
            <span className={cn(
              "flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider",
              "bg-charcoal-700/50 text-charcoal-400"
            )}>
              {getChannelIcon(message.channel)}
              <span className="hidden sm:inline">{getChannelLabel(message.channel)}</span>
            </span>
          </div>

          <Timestamp time={formatTimestamp(message.occurred_at)} />
        </div>

        {/* Content */}
        <div className={cn(
          "text-sm leading-relaxed whitespace-pre-wrap",
          isCustomer && "text-cream-200",
          isUs && "text-cream-300",
          isInternal && "text-rust-200/90"
        )}>
          {message.html_content ? (
            <div
              className="prose prose-sm prose-invert max-w-none"
              dangerouslySetInnerHTML={{ __html: message.html_content }}
            />
          ) : (
            message.content
          )}
        </div>

        {/* Mentions */}
        {message.mentions && message.mentions.length > 0 && (
          <div className="flex items-center gap-2 mt-3">
            {message.mentions.map((mention) => (
              <span
                key={mention.id}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-charcoal-700 text-xs text-cream-300"
              >
                @{mention.user_name}
              </span>
            ))}
          </div>
        )}

        {/* Attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <div className="mt-3 space-y-2">
            <div className="flex items-center gap-1.5 text-xs text-charcoal-400 font-mono uppercase tracking-wider">
              <Paperclip className="w-3 h-3" />
              <span>{message.attachments.length} attachment{message.attachments.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {message.attachments.map((attachment) => (
                <AttachmentPreview key={attachment.id} attachment={attachment} />
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className={cn(
            "p-4 rounded-none",
            i % 2 === 0 ? "bg-charcoal-800 mr-24" : "bg-charcoal-900 ml-24"
          )}
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="h-4 w-24 bg-charcoal-700 rounded" />
            <div className="h-4 w-12 bg-charcoal-700 rounded" />
          </div>
          <div className="space-y-2">
            <div className="h-4 w-full bg-charcoal-700 rounded" />
            <div className="h-4 w-3/4 bg-charcoal-700 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ConversationThread({ messages, isLoading }: ConversationThreadProps) {
  const endRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messages.length > 0 && endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length]);

  if (isLoading) {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <LoadingSkeleton />
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="text-center">
          <MessageSquare className="w-12 h-12 text-charcoal-600 mx-auto mb-3" />
          <p className="text-charcoal-400 text-sm">No messages in this thread yet</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="space-y-4 max-w-3xl">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
