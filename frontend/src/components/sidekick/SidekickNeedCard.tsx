import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Zap, HelpCircle, ChevronDown, ChevronUp, Send, Clock, AlertCircle } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { RefCode, Timestamp, Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import type { TodayQueueItem, AgentQuestion } from '@/lib/api';

interface SidekickNeedCardProps {
  item: TodayQueueItem & {
    agent_run_id?: string | null;
    agent_questions?: AgentQuestion[] | null;
    agent_context?: string | null;
  };
  onSnooze: () => void;
}

// Format time ago
function timeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 60) return `T-${minutes}m`;
  if (hours < 24) return `T-${hours}h`;
  return `T-${days}d`;
}

export function SidekickNeedCard({ item, onSnooze, onHover }: SidekickNeedCardProps & { onHover?: () => void }) {
  const [expanded, setExpanded] = useState(false); // Start collapsed
  const questionCount = item.agent_questions?.length || 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative group"
      onMouseEnter={onHover}
    >
      {/* Sidekick Banner */}
      <div className="absolute -top-3 left-0 right-0 flex items-center gap-2 z-10">
        <div className="bg-rust-500 text-charcoal-900 px-3 py-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest font-bold">
          <Zap className="w-3 h-3 fill-charcoal-900" />
          <span>Sidekick Needs Help</span>
        </div>
        <div className="h-[1px] flex-1 bg-rust-500/30"></div>
      </div>

      {/* Card Container with rust accent */}
      <div className="mt-4 border-2 border-rust-500/50 bg-gradient-to-br from-charcoal-800 to-charcoal-900 p-6 relative overflow-hidden">
        {/* Subtle background pattern */}
        <div className="absolute inset-0 opacity-5 pointer-events-none">
          <div className="absolute inset-0" style={{
            backgroundImage: `repeating-linear-gradient(
              45deg,
              transparent,
              transparent 10px,
              rgba(194, 65, 12, 0.3) 10px,
              rgba(194, 65, 12, 0.3) 11px
            )`
          }} />
        </div>

        {/* Header Row */}
        <div className="flex items-center gap-4 mb-4 relative z-10">
          <Pulse active continuous className="text-rust-500" />
          <div className="flex items-center gap-3 font-mono text-[10px] tracking-widest text-rust-400 uppercase">
            <RefCode className="text-rust-500 font-bold">{item.id.slice(0, 8).toUpperCase()}</RefCode>
            <span>//</span>
            <Timestamp time={timeAgo(item.created_at)} className="text-rust-400/80" />
            <span>//</span>
            <span className="text-rust-300">{questionCount} QUESTION{questionCount !== 1 ? 'S' : ''}</span>
          </div>

          {/* Quick action */}
          <div className="ml-auto flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={onSnooze}
              className="p-1.5 text-charcoal-400 hover:text-cream-200 hover:bg-charcoal-700 rounded transition-colors"
              title="Snooze for 24h"
            >
              <Clock className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Customer Name */}
        <div className="flex items-start justify-between gap-4 mb-4 relative z-10">
          <div>
            <h2 className="font-serif text-3xl sm:text-4xl text-cream-100 mb-1 tracking-tight">
              Re: {item.customer_name}
            </h2>
            <p className="text-sm text-rust-300 font-medium">
              {item.headline}
            </p>
          </div>
        </div>

        {/* Context Box */}
        {item.agent_reasoning && (
          <div className="relative border-l-2 border-rust-500 pl-4 py-2 mb-6 bg-rust-900/20">
            <div className="absolute -left-0.5 -top-2 bg-charcoal-800 text-rust-500 font-mono text-[9px] uppercase tracking-widest px-1 flex items-center gap-1">
              <AlertCircle className="w-2.5 h-2.5" />
              <span>Why I'm asking</span>
            </div>
            <p className="text-cream-300 text-sm leading-relaxed mt-1">
              {item.agent_reasoning}
            </p>
          </div>
        )}

        {/* Questions Preview */}
        <div className="space-y-3 mb-6 relative z-10">
          {item.agent_questions?.slice(0, expanded ? 3 : 1).map((q, index) => (
            <div
              key={q.id}
              className="flex items-start gap-3 bg-charcoal-900/50 border border-charcoal-700 p-3"
            >
              <div className="flex items-center justify-center w-5 h-5 rounded-full bg-rust-500/20 text-rust-400 text-xs font-bold shrink-0 mt-0.5">
                {index + 1}
              </div>
              <div className="flex-1">
                <p className="text-cream-200 text-sm leading-relaxed">
                  {q.text}
                </p>
                {q.context && (
                  // Compact preview: strip the "## " section markers + collapse to one line
                  // (the full structured context renders in the FocusPane on open).
                  <p className="text-charcoal-400 text-xs mt-1 line-clamp-2">
                    {q.context.replace(/^##\s+/gm, '').replace(/\s*\n\s*/g, ' · ').trim()}
                  </p>
                )}
              </div>
            </div>
          ))}

          {questionCount > 3 && !expanded && (
            <div className="text-xs text-charcoal-400 pl-8">
              +{questionCount - 1} more questions
            </div>
          )}
        </div>

        {/* Expand/Collapse */}
        {questionCount > 1 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-2 text-xs font-mono text-charcoal-400 hover:text-cream-200 transition-colors mb-4"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            <span className="uppercase tracking-widest">
              {expanded ? 'Show less' : `Show all ${questionCount} questions`}
            </span>
          </button>
        )}

        {/* Action Button */}
        <div className="flex items-center justify-between pt-4 border-t border-charcoal-700/50 relative z-10">
          <p className="text-xs text-charcoal-500 italic">
            Answer these questions to help Sidekick complete the handoff
          </p>
          <NavLink
            to={`/app/needs/${item.id}`}
            className="inline-flex items-center gap-2 bg-rust-500 hover:bg-rust-400 text-charcoal-900 px-4 py-2 font-mono text-xs uppercase tracking-widest font-bold transition-colors"
          >
            <HelpCircle className="w-4 h-4" />
            <span>Answer Questions</span>
          </NavLink>
        </div>
      </div>
    </motion.div>
  );
}

export default SidekickNeedCard;
