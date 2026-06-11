import React, { useState, useRef, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useWorkspace } from '@/lib/workspace';
import { useAuth } from '@/lib/auth';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

// ─── Types ───────────────────────────────────────────────────────────────────

interface SweepFinding {
  customer_name: string;
  signal_kind: string;
  signal_state: string;
  sentence: string;
}

interface SweepResult {
  customers_checked: number;
  signals_created: number;
  skipped_dedup: number;
  errors: number;
  findings: SweepFinding[];
}

interface DrainTask {
  task_id: string;
  task_type: string;
  customer_name: string;
  status: string;
  play?: string | null;
  duration_ms: number;
  error?: string | null;
}

interface DrainResult {
  processed: number;
  duration_ms?: number;
  tasks?: DrainTask[];
  error?: string;
}

interface InboundEmailResult {
  profile: string;
  customer_name?: string;
  category?: string;
  sentiment?: string;
  complexity?: string;
  summary?: string;
  risk_level?: string;
  escalated?: boolean;
  risk_factors?: string[];
  draft_subject?: string;
  draft_preview?: string;
  error?: string;
}

interface InboundResult {
  processed: number;
  duration_ms?: number;
  results?: InboundEmailResult[];
  error?: string;
}

interface RunEntry {
  id: number;
  label: string;
  startMs: number;      // epoch ms when request was sent
  endMs?: number;       // epoch ms when response arrived
  sweep?: SweepResult | null;
  drain?: DrainResult | null;
  inbound?: InboundResult | null;
  error?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function nowTs(): string {
  return new Date().toLocaleTimeString('en-US', { hour12: false });
}

function fmtDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m${s % 60}s`;
}

function stateClass(state: string): string {
  if (state === 'risk') return 'text-signal-risk';
  if (state === 'warn') return 'text-signal-warn';
  return 'text-fg-400';
}

function riskClass(level?: string): string {
  if (level === 'high') return 'text-signal-risk';
  if (level === 'medium') return 'text-signal-warn';
  return 'text-fg-400';
}

interface QueueTask {
  id: string;
  customer_name?: string;
  customer_id?: string;
  task_type: string;
  trigger_type: string;
  status: string;
  priority: number;
  scheduled_for?: string;
  attempts?: number;
  created_at?: string;
}

function taskStatusClass(status: string): string {
  if (status === 'failed') return 'text-signal-risk';
  if (status === 'waiting') return 'text-signal-warn';
  if (status === 'in_progress') return 'text-accent';
  if (status === 'done') return 'text-fg-400';
  return 'text-fg-200'; // pending
}

// ─── Entry renderer ───────────────────────────────────────────────────────────

function RunBlock({ entry }: { entry: RunEntry }) {
  const wallTime = entry.endMs
    ? fmtDuration(entry.endMs - entry.startMs)
    : null;
  const startTs = new Date(entry.startMs).toLocaleTimeString('en-US', { hour12: false });

  return (
    <div className="border-b border-border pb-3 mb-3 last:mb-0 last:pb-0 last:border-0">
      {/* run header */}
      <div className="flex items-center justify-between mb-1">
        <span className="text-fg-400 font-mono text-xs">── {entry.label} ──</span>
        <span className="text-fg-400 font-mono text-xs">
          {startTs}{wallTime ? ` · ${wallTime}` : ' · running…'}
        </span>
      </div>

      {entry.error && (
        <p className="font-mono text-xs text-signal-risk pl-2">{entry.error}</p>
      )}

      {/* SWEEP block */}
      {entry.sweep !== undefined && entry.sweep !== null && (
        <div className="pl-2 mb-1">
          <span className="text-accent font-mono text-xs font-semibold mr-2">SWEEP</span>
          <span className="font-mono text-xs text-fg-200">
            customers:{entry.sweep.customers_checked}{'  '}
            signals:{entry.sweep.signals_created}{'  '}
            skipped:{entry.sweep.skipped_dedup}{'  '}
            errors:{entry.sweep.errors}
          </span>
          {entry.sweep.findings.map((f, i) => (
            <div key={i} className="pl-4 mt-0.5">
              <span className={cn('font-mono text-xs font-semibold mr-1', stateClass(f.signal_state))}>
                ↳ {f.signal_kind.toUpperCase()}
              </span>
              <span className={cn('font-mono text-xs mr-2', stateClass(f.signal_state))}>
                {f.signal_state.toUpperCase()}
              </span>
              <span className="font-mono text-xs text-fg-200">{f.customer_name}</span>
              <div className="pl-4 font-mono text-xs text-fg-400">{f.sentence}</div>
            </div>
          ))}
        </div>
      )}

      {/* DRAIN block */}
      {entry.drain !== undefined && entry.drain !== null && (
        <div className="pl-2">
          <span className="text-fg-300 font-mono text-xs font-semibold mr-2">DRAIN</span>
          <span className="font-mono text-xs text-fg-200">
            processed:{entry.drain.processed}
            {entry.drain.duration_ms != null && `  wall:${fmtDuration(entry.drain.duration_ms)}`}
          </span>
          {entry.drain.error && (
            <span className="font-mono text-xs text-signal-risk ml-2">({entry.drain.error})</span>
          )}
          {entry.drain.tasks && entry.drain.tasks.map((t, i) => (
            <div key={i} className="pl-4 mt-0.5 flex items-baseline gap-2">
              <span className={cn('font-mono text-xs font-semibold', t.status === 'failed' ? 'text-signal-risk' : t.status === 'waiting' ? 'text-signal-warn' : 'text-fg-300')}>
                ↳ {t.status.toUpperCase()}
              </span>
              <span className="font-mono text-xs text-fg-200">{t.customer_name}</span>
              {t.play && <span className="font-mono text-xs text-accent">{t.play}</span>}
              <span className="font-mono text-xs text-fg-400">{fmtDuration(t.duration_ms)}</span>
              {t.error && <span className="font-mono text-xs text-signal-risk truncate max-w-xs">{t.error}</span>}
            </div>
          ))}
        </div>
      )}

      {/* INBOUND block */}
      {entry.inbound !== undefined && entry.inbound !== null && (
        <div className="pl-2">
          <span className="text-accent font-mono text-xs font-semibold mr-2">INBOUND</span>
          <span className="font-mono text-xs text-fg-200">
            processed:{entry.inbound.processed}
            {entry.inbound.duration_ms != null && `  wall:${fmtDuration(entry.inbound.duration_ms)}`}
          </span>
          {entry.inbound.error && (
            <span className="font-mono text-xs text-signal-risk ml-2">({entry.inbound.error})</span>
          )}
          {entry.inbound.results && entry.inbound.results.map((r, i) => (
            <div key={i} className="pl-4 mt-1.5">
              {r.error ? (
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-xs font-semibold text-fg-300">[{r.profile}]</span>
                  <span className="font-mono text-xs text-signal-risk truncate max-w-md">{r.error}</span>
                </div>
              ) : (
                <>
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="font-mono text-xs font-semibold text-fg-300">[{r.profile}]</span>
                    <span className={cn('font-mono text-xs font-semibold', riskClass(r.risk_level))}>
                      ↳ {(r.risk_level || 'low').toUpperCase()}
                    </span>
                    {r.escalated && (
                      <span className="font-mono text-xs font-semibold text-signal-risk">⚡ESCALATED</span>
                    )}
                    <span className="font-mono text-xs text-fg-200">{r.customer_name}</span>
                    <span className="font-mono text-xs text-fg-400">
                      {[r.category, r.sentiment, r.complexity].filter(Boolean).join(' · ')}
                    </span>
                  </div>
                  {r.summary && (
                    <div className="pl-4 font-mono text-xs text-fg-200">{r.summary}</div>
                  )}
                  {r.draft_preview && (
                    <div className="pl-4 font-mono text-xs text-fg-400 truncate max-w-2xl italic">
                      draft: {r.draft_preview}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PipelineTest() {
  const { workspaceId } = useWorkspace();
  const { user } = useAuth();

  const [runCount, setRunCount] = useState<number>(1);
  const [running, setRunning] = useState(false);
  const [entries, setEntries] = useState<RunEntry[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  // Queue viewer state
  const [queueTasks, setQueueTasks] = useState<QueueTask[]>([]);
  const [queueCounts, setQueueCounts] = useState<Record<string, number>>({});
  const [queueFilter, setQueueFilter] = useState<string>(''); // customer_id, '' = all
  const [queueLoading, setQueueLoading] = useState(false);

  // Scroll to bottom of log after appending
  const scrollLog = useCallback(() => {
    setTimeout(() => {
      if (logRef.current) {
        logRef.current.scrollTop = logRef.current.scrollHeight;
      }
    }, 30);
  }, []);

  const appendEntry = useCallback((entry: RunEntry) => {
    setEntries(prev => [...prev, entry]);
    scrollLog();
  }, [scrollLog]);

  const finalizeEntry = useCallback((id: number, patch: Partial<RunEntry>) => {
    setEntries(prev => prev.map(e => e.id === id ? { ...e, ...patch } : e));
    scrollLog();
  }, [scrollLog]);

  async function getToken(): Promise<string | null> {
    try {
      return (await user?.getIdToken()) ?? null;
    } catch {
      return null;
    }
  }

  function headers(token: string | null): Record<string, string> {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) h['Authorization'] = `Bearer ${token}`;
    return h;
  }

  // ── shared fetch helper ──────────────────────────────────────────────────────
  async function callPipelineTest(steps: string[], label: string) {
    const token = await getToken();
    const id = nextId.current++;
    const startMs = Date.now();
    // Add placeholder immediately so user sees "running…"
    appendEntry({ id, label, startMs });
    try {
      const res = await fetch(`${PYTHON_URL}/agents/pipeline-test`, {
        method: 'POST',
        headers: headers(token),
        body: JSON.stringify({ workspace_id: workspaceId, steps }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error?.message || `HTTP ${res.status}`);
      finalizeEntry(id, { endMs: Date.now(), sweep: data.sweep ?? null, drain: data.drain ?? null });
    } catch (e) {
      finalizeEntry(id, { endMs: Date.now(), error: String(e) });
    }
  }

  // ── RESET button ────────────────────────────────────────────────────────────
  async function handleReset() {
    if (!workspaceId || running) return;
    setRunning(true);
    const token = await getToken();
    const id = nextId.current++;
    const startMs = Date.now();
    appendEntry({ id, label: 'RESET', startMs });
    try {
      const res = await fetch(`${PYTHON_URL}/agents/pipeline-test/reset`, {
        method: 'POST',
        headers: headers(token),
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error?.message || `HTTP ${res.status}`);
      finalizeEntry(id, {
        endMs: Date.now(),
        sweep: {
          customers_checked: 0,
          signals_created: 0,
          skipped_dedup: 0,
          errors: 0,
          findings: [{
            customer_name: 'workspace',
            signal_kind: 'reset',
            signal_state: 'ok',
            sentence: `Superseded ${data.signals_superseded} signal(s), resolved ${data.needs_resolved} need(s)`,
          }],
        },
      });
    } catch (e) {
      finalizeEntry(id, { endMs: Date.now(), error: String(e) });
    } finally {
      setRunning(false);
    }
  }

  // ── SWEEP button ────────────────────────────────────────────────────────────
  async function handleSweep() {
    if (!workspaceId || running) return;
    setRunning(true);
    await callPipelineTest(['sweep'], 'SWEEP');
    setRunning(false);
  }

  // ── DRAIN button ────────────────────────────────────────────────────────────
  async function handleDrain() {
    if (!workspaceId || running) return;
    setRunning(true);
    await callPipelineTest(['drain'], 'DRAIN');
    setRunning(false);
  }

  // ── INBOUND button ──────────────────────────────────────────────────────────
  async function handleInbound() {
    if (!workspaceId || running) return;
    setRunning(true);
    const token = await getToken();
    const id = nextId.current++;
    const startMs = Date.now();
    appendEntry({ id, label: 'INBOUND', startMs });
    try {
      const res = await fetch(`${PYTHON_URL}/agents/pipeline-test/inbound`, {
        method: 'POST',
        headers: headers(token),
        body: JSON.stringify({ workspace_id: workspaceId, count: 12 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error?.message || `HTTP ${res.status}`);
      finalizeEntry(id, {
        endMs: Date.now(),
        inbound: {
          processed: data.processed ?? 0,
          duration_ms: data.duration_ms,
          results: data.results ?? [],
        },
      });
    } catch (e) {
      finalizeEntry(id, { endMs: Date.now(), error: String(e) });
    } finally {
      setRunning(false);
    }
  }

  // ── PIPELINE button ─────────────────────────────────────────────────────────
  async function handlePipeline() {
    if (!workspaceId || running) return;
    setRunning(true);
    for (let i = 1; i <= runCount; i++) {
      const label = runCount === 1 ? 'PIPELINE' : `RUN ${i}/${runCount}`;
      await callPipelineTest(['sweep', 'drain'], label);
    }
    setRunning(false);
  }

  // ── QUEUE viewer ──────────────────────────────────────────────────────────
  async function loadQueue() {
    if (!workspaceId) return;
    setQueueLoading(true);
    const token = await getToken();
    try {
      const res = await fetch(`${PYTHON_URL}/agents/pipeline-test/queue`, {
        method: 'POST',
        headers: headers(token),
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      const data = await res.json();
      if (res.ok) {
        setQueueTasks(data.tasks ?? []);
        setQueueCounts(data.counts ?? {});
      }
    } catch {
      // non-fatal
    } finally {
      setQueueLoading(false);
    }
  }

  // Distinct customers present in the queue, for the filter dropdown.
  const queueCustomers = Array.from(
    new Map(queueTasks.filter(t => t.customer_id).map(t => [t.customer_id, t.customer_name])).entries()
  );
  const filteredTasks = queueFilter
    ? queueTasks.filter(t => t.customer_id === queueFilter)
    : queueTasks;

  const RUN_COUNTS = [1, 5, 10, 20];

  return (
    <div className="flex flex-col h-full p-6 gap-4 font-mono">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div>
          <h1 className="font-display text-fg-100 text-base font-semibold tracking-widest uppercase">
            Pipeline · Test Console
          </h1>
          <p className="text-fg-400 text-xs mt-0.5">
            Workspace:{' '}
            <span className="text-fg-300">{workspaceId ? workspaceId.slice(0, 18) + '…' : '—'}</span>
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleSweep}
            disabled={running || !workspaceId}
            className={cn(
              'btn-hud text-xs px-3 py-1.5',
              (running || !workspaceId) && 'opacity-40 cursor-not-allowed'
            )}
          >
            SWEEP
          </button>
          <button
            onClick={handleDrain}
            disabled={running || !workspaceId}
            className={cn(
              'btn-hud text-xs px-3 py-1.5',
              (running || !workspaceId) && 'opacity-40 cursor-not-allowed'
            )}
          >
            DRAIN
          </button>
          <button
            onClick={handlePipeline}
            disabled={running || !workspaceId}
            className={cn(
              'btn-hud text-xs px-3 py-1.5 text-accent',
              (running || !workspaceId) && 'opacity-40 cursor-not-allowed'
            )}
          >
            PIPELINE
          </button>
          <button
            onClick={handleInbound}
            disabled={running || !workspaceId}
            title="Fire a batch of fake inbound emails through the light support lane"
            className={cn(
              'btn-hud text-xs px-3 py-1.5',
              (running || !workspaceId) && 'opacity-40 cursor-not-allowed'
            )}
          >
            INBOUND
          </button>
          <span className="text-border mx-1">|</span>
          <button
            onClick={handleReset}
            disabled={running || !workspaceId}
            title="Supersede sweep signals + resolve needs so the next run detects them fresh"
            className={cn(
              'btn-hud text-xs px-3 py-1.5 text-fg-400',
              (running || !workspaceId) && 'opacity-40 cursor-not-allowed'
            )}
          >
            RESET STATE
          </button>
        </div>

        {/* Run count selector */}
        <div className="flex items-center gap-1 text-fg-400 text-xs">
          <span className="mr-1">Runs:</span>
          {RUN_COUNTS.map(n => (
            <button
              key={n}
              onClick={() => setRunCount(n)}
              disabled={running}
              className={cn(
                'btn-hud text-xs px-2 py-1',
                runCount === n ? 'text-accent' : 'text-fg-400',
                running && 'opacity-40 cursor-not-allowed'
              )}
            >
              {n}
            </button>
          ))}
        </div>

        {/* Spacer + clear */}
        <div className="ml-auto">
          <button
            onClick={() => setEntries([])}
            disabled={running}
            className={cn(
              'btn-hud text-xs px-3 py-1.5 text-fg-400',
              running && 'opacity-40 cursor-not-allowed'
            )}
          >
            CLEAR LOG
          </button>
        </div>
      </div>

      {/* Log area */}
      <div className="flex-1 min-h-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-fg-300 text-xs uppercase tracking-widest">
            Output{entries.length > 0 ? ` · ${entries.length} run${entries.length !== 1 ? 's' : ''}` : ''}
          </span>
          {running && (
            <span className="text-accent text-xs animate-pulse">● running…</span>
          )}
        </div>
        <div
          ref={logRef}
          className={cn(
            'bg-surface-2 border border-border rounded p-4',
            'overflow-y-auto max-h-[60vh]',
          )}
        >
          {entries.length === 0 ? (
            <p className="text-fg-400 text-xs">No runs yet. Press SWEEP, DRAIN, PIPELINE, or INBOUND.</p>
          ) : (
            entries.map(entry => <RunBlock key={entry.id} entry={entry} />)
          )}
        </div>
      </div>

      {/* Queue viewer */}
      <div className="min-h-0">
        <div className="flex items-center gap-3 mb-2 flex-wrap">
          <span className="text-fg-300 text-xs uppercase tracking-widest">Agent Task Queue</span>
          <button
            onClick={loadQueue}
            disabled={queueLoading || !workspaceId}
            className={cn('btn-hud text-xs px-2.5 py-1', (queueLoading || !workspaceId) && 'opacity-40 cursor-not-allowed')}
          >
            {queueLoading ? 'LOADING…' : 'REFRESH'}
          </button>
          {/* status rollup */}
          {Object.entries(queueCounts).map(([status, n]) => (
            <span key={status} className={cn('font-mono text-xs', taskStatusClass(status))}>
              {status}:{n}
            </span>
          ))}
          {/* customer filter */}
          {queueCustomers.length > 0 && (
            <select
              value={queueFilter}
              onChange={e => setQueueFilter(e.target.value)}
              className="ml-auto bg-surface-2 border border-border text-fg-200 text-xs font-mono px-2 py-1 rounded"
            >
              <option value="">all customers</option>
              {queueCustomers.map(([id, name]) => (
                <option key={id} value={id ?? ''}>{name}</option>
              ))}
            </select>
          )}
        </div>
        <div className="bg-surface-2 border border-border rounded p-3 overflow-y-auto max-h-[30vh]">
          {filteredTasks.length === 0 ? (
            <p className="text-fg-400 text-xs">
              {queueTasks.length === 0 ? 'Queue empty or not loaded. Press REFRESH.' : 'No tasks for this customer.'}
            </p>
          ) : (
            filteredTasks.map(t => (
              <div key={t.id} className="flex items-baseline gap-2 py-0.5 border-b border-border/40 last:border-0">
                <span className={cn('font-mono text-xs font-semibold w-20 shrink-0', taskStatusClass(t.status))}>
                  {t.status}
                </span>
                <span className="font-mono text-xs text-fg-200 w-40 shrink-0 truncate">{t.customer_name || '—'}</span>
                <span className="font-mono text-xs text-accent w-28 shrink-0 truncate">{t.task_type}</span>
                <span className="font-mono text-xs text-fg-400 shrink-0">p{t.priority}</span>
                <span className="font-mono text-xs text-fg-400 shrink-0">{t.trigger_type}</span>
                {(t.attempts ?? 0) > 0 && (
                  <span className="font-mono text-xs text-fg-400 shrink-0">×{t.attempts}</span>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
