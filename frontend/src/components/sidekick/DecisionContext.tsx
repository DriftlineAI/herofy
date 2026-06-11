import { useMemo } from 'react';

/**
 * Renders a HITL question's context. The orchestrator's decision pause emits a structured context
 * with "## " section headers (What changed / Evidence / Drafted email — a stable backend contract,
 * see worker/agent.py), so we split it into readable cards instead of one dense block; the email
 * section gets its own subject + body treatment. Plain (non-structured) contexts fall back to a
 * simple paragraph. Shared by the Bridge FocusPane and the SidekickQuestion answer screen.
 */
export function DecisionContext({ context, className }: { context: string; className?: string }) {
  const sections = useMemo(() => {
    if (!context.includes('## ')) return null;
    return context
      .split(/\n(?=## )/)
      .map((block) => {
        const m = block.match(/^##\s+(.+?)\r?\n([\s\S]*)$/);
        return m ? { label: m[1].trim(), body: m[2].trim() } : { label: '', body: block.trim() };
      })
      .filter((s) => s.body);
  }, [context]);

  if (!sections) {
    return (
      <p className={`font-sans text-[14px] not-italic font-medium leading-relaxed text-fg-300 max-w-[600px] ${className ?? ''}`}>
        {context}
      </p>
    );
  }

  return (
    <div className={`max-w-[600px] space-y-3 ${className ?? ''}`}>
      {sections.map((s, i) => {
        if (/email/i.test(s.label)) {
          const sm = s.body.match(/^Subject:\s*(.+?)\r?\n\r?\n([\s\S]*)$/);
          const subject = sm ? sm[1].trim() : null;
          const body = sm ? sm[2].trim() : s.body;
          return (
            <div key={i} className="overflow-hidden rounded-md border border-border border-l-4 border-l-accent bg-surface">
              <div className="border-b border-border bg-surface-2 px-4 py-2">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-widest text-accent">
                  Drafted email
                </span>
              </div>
              <div className="px-4 py-3">
                {subject && (
                  <div className="mb-2.5 flex items-baseline gap-2 border-b border-border pb-2">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-fg-400">Subject</span>
                    <span className="text-[13.5px] font-medium not-italic text-fg-100">{subject}</span>
                  </div>
                )}
                <p className="font-sans text-[13.5px] not-italic text-fg-200 leading-relaxed whitespace-pre-wrap">
                  {body}
                </p>
              </div>
            </div>
          );
        }
        return (
          <div key={i} className="rounded-md border border-border bg-surface px-4 py-3">
            {s.label && (
              <div className="mb-1.5 font-mono text-[10px] font-semibold uppercase tracking-widest text-fg-400">
                {s.label}
              </div>
            )}
            <p className="font-sans text-[13px] not-italic text-fg-300 leading-relaxed whitespace-pre-wrap">
              {s.body}
            </p>
          </div>
        );
      })}
    </div>
  );
}

export default DecisionContext;
