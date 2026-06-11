import React from 'react';
import { Zap } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * RefCode — HUD chrome element for reference codes
 * Uses Share Tech Mono, uppercase, 0.25em letter-spacing
 */
export function RefCode({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn(
      "font-mono text-[11px] text-fg-400 uppercase tracking-[0.25em]",
      className
    )}>
      {children}
    </span>
  );
}

/**
 * Timestamp — HUD chrome element for time display
 */
export function Timestamp({ time, className }: { time: string; className?: string }) {
  return (
    <span className={cn(
      "font-mono text-[11px] text-fg-400 uppercase tracking-[0.25em]",
      className
    )}>
      {time}
    </span>
  );
}

/**
 * Pulse — animated indicator dot
 * Uses accent color (gold) with optional continuous ping animation
 */
export function Pulse({
  active = true,
  className,
  continuous = false
}: {
  active?: boolean;
  className?: string;
  continuous?: boolean
}) {
  if (!active) return null;
  return (
    <span className={cn("relative flex h-2 w-2", className)}>
      {continuous && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
      )}
      <span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
    </span>
  );
}

/**
 * MissionStamp — HUD chrome label/badge
 * Uses Share Tech Mono, uppercase, 0.25em letter-spacing
 */
export function MissionStamp({ type, className }: { type: string; className?: string }) {
  return (
    <span className={cn(
      "inline-block font-mono text-[11px] tracking-[0.25em] uppercase border border-border px-2 py-0.5 text-fg-300",
      className
    )}>
      {type}
    </span>
  );
}

/**
 * IntelBar — horizontal bar chart indicator
 * Uses accent color for filled segments
 */
export function IntelBar({ value, max = 5, className }: { value: number; max?: number; className?: string }) {
  return (
    <div className={cn("flex items-center gap-[2px]", className)}>
      {Array.from({ length: max }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-1.5 w-4 transition-colors duration-500",
            i < value ? "bg-accent" : "bg-border"
          )}
        />
      ))}
    </div>
  );
}

/**
 * SparkBar — mini bar chart for activity visualization
 */
export function SparkBar({ values, className }: { values: number[]; className?: string }) {
  const max = Math.max(...values, 1);
  return (
    <div className={cn("flex items-end gap-[1px] h-8", className)}>
      {values.map((v, i) => (
        <div
          key={i}
          className="w-1.5 bg-accent/40 hover:bg-accent transition-colors"
          style={{ height: `${(v / max) * 100}%` }}
        />
      ))}
    </div>
  );
}

/**
 * TickerItem — HUD chrome element for ticker/status bar
 * Uses Share Tech Mono, uppercase, 0.25em letter-spacing
 */
export function TickerItem({
  label,
  value,
  trend,
  className,
  isDay // Deprecated - kept for compatibility, no longer used
}: {
  label: string;
  value: string;
  trend?: 'up' | 'down' | 'neutral';
  className?: string;
  isDay?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 px-6 border-r border-border h-full whitespace-nowrap">
      <span className="font-mono text-[11px] uppercase tracking-[0.25em] text-fg-400">
        {label}
      </span>
      <span className={cn("font-mono text-sm text-fg-200", className)}>
        {value}
      </span>
      {trend === 'up' && <span className="text-[9px] text-signal-ok">▲</span>}
      {trend === 'down' && <span className="text-[9px] text-signal-bad">▼</span>}
    </div>
  );
}

/**
 * Sidekick — HUD pane / log entry style AI assistant surface
 *
 * Features:
 * - 4px gold left rail
 * - Mono header strip with live pulse and ref code
 * - Surface background with Lift bezel
 */
export function Sidekick({
  children,
  title = "SIDEKICK",
  refCode,
  className
}: {
  children: React.ReactNode;
  title?: string;
  refCode?: string;
  className?: string
}) {
  return (
    <section className={cn(
      "relative border border-border border-l-4 border-l-accent bg-surface shadow-lift",
      className
    )}>
      {/* Header strip */}
      <header className="flex items-center gap-3.5 px-5 py-3 border-b border-rule font-mono uppercase tracking-[0.3em] text-[11.5px] font-semibold text-accent">
        <span className="h-1.5 w-1.5 rounded-full bg-accent animate-[hud-pulse_2.4s_ease-in-out_infinite]"></span>
        <span>{title}</span>
        <span className="flex-1"></span>
        {refCode && (
          <span className="text-fg-400 tracking-[0.25em] font-normal">{refCode}</span>
        )}
      </header>

      {/* Body */}
      <div className="px-5 py-5 text-fg-200 leading-relaxed font-sans font-medium">
        {children}
      </div>
    </section>
  );
}

/**
 * SidekickLegacy — Original inline Sidekick style (for migration)
 */
export function SidekickLegacy({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("relative border-l-4 border-accent pl-4 py-1 my-4", className)}>
      <div className="absolute -left-1 -top-3 bg-page text-accent font-mono text-[11px] uppercase tracking-[0.25em] px-1 flex items-center gap-1 font-semibold">
        <Zap className="w-3 h-3 fill-accent" />
        <span>Sidekick</span>
      </div>
      <p className="text-fg-200 text-sm leading-relaxed font-sans font-medium">
        {children}
      </p>
    </div>
  );
}
