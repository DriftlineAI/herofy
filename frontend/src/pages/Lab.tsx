import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useWorkspace } from '@/lib/workspace';
import { useAuth } from '@/lib/auth';
import {
  useWorkspaceNotifications,
  useAgentStatusRealtime,
  useAgentOutputsRealtime,
  useAgentStepsRealtime,
  type AgentOutput,
} from '@/lib/realtime-hooks';
import {
  WORKER_HEAD,
  WORKER_TAIL,
  PLAYS,
  isPlayRoot,
  playForStep,
  type DagNode,
  type NodeState,
} from '@/lib/orchestrator-dag';
import { useGetUserById } from '@/dataconnect-generated/react';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

type SeedProfile = 'full' | 'lane1' | 'lane2';

const SEED_PROFILES: { key: SeedProfile; label: string }[] = [
  { key: 'full', label: 'full · all 13' },
  { key: 'lane1', label: 'lane1 · handoffs' },
  { key: 'lane2', label: 'lane2 · portfolio' },
];

type Scenario = 'risk' | 'support' | 'meeting' | 'hitl' | 'all';

const SCENARIOS: { key: Scenario; label: string; hint: string }[] = [
  { key: 'risk', label: 'Run · Risk/Save', hint: 'one at-risk account → full save play' },
  { key: 'support', label: 'Run · Support', hint: 'inbound issue → support play' },
  { key: 'meeting', label: 'Run · Meeting', hint: 'upcoming call → meeting brief' },
  { key: 'hitl', label: 'Run · HITL', hint: 'pauses for a CSM decision' },
  { key: 'all', label: 'Run · Day', hint: 'several accounts, back-to-back' },
];

// ─── status → UI mapping ─────────────────────────────────────────────────────

function statusTone(status?: string): string {
  if (status === 'completed') return 'text-signal-ok';
  if (status === 'failed') return 'text-signal-risk';
  if (status === 'waiting_for_input' || status === 'paused') return 'text-signal-warn';
  return 'text-accent';
}

function isTerminal(status?: string): boolean {
  return status === 'completed' || status === 'failed';
}

// ─── DAG node renderer ───────────────────────────────────────────────────────

function nodeMarker(state: NodeState): { glyph: string; cls: string } {
  if (state === 'done') return { glyph: '●', cls: 'text-signal-ok' };
  if (state === 'active') return { glyph: '◆', cls: 'text-accent animate-pulse' };
  return { glyph: '○', cls: 'text-fg-400' };
}

function TraceNode({
  node,
  depth,
  stateFor,
}: {
  node: DagNode;
  depth: number;
  stateFor: (id: string) => NodeState;
}) {
  const state = stateFor(node.id);
  const marker = nodeMarker(state);
  return (
    <div>
      <div
        className="flex items-baseline gap-2 py-0.5 font-mono text-xs"
        style={{ paddingLeft: `${depth * 18}px` }}
      >
        <span className={cn('w-3 text-center', marker.cls)}>{marker.glyph}</span>
        <span
          className={cn(
            state === 'active' && 'text-accent font-semibold',
            state === 'done' && 'text-fg-200',
            state === 'pending' && 'text-fg-400',
          )}
        >
          {node.label}
          {node.loop && <span className="text-fg-400 ml-1">⟲</span>}
        </span>
        {state === 'active' && (
          <span className="text-fg-400 text-[10px] uppercase tracking-wide">running</span>
        )}
      </div>
      {node.children?.map((c, i) => (
        <TraceNode key={`${c.id}-${i}`} node={c} depth={depth + 1} stateFor={stateFor} />
      ))}
    </div>
  );
}

// ─── Output card (what each agent/LLM actually produced) ─────────────────────

function prettyIfJson(text: string): string {
  const t = text.trim();
  if (!(t.startsWith('{') || t.startsWith('['))) return text;
  try {
    return JSON.stringify(JSON.parse(t), null, 2);
  } catch {
    return text;
  }
}

const COLLAPSE_CHARS = 600;

function OutputCard({ out }: { out: AgentOutput }) {
  const [expanded, setExpanded] = useState(false);
  const isTool = out.kind === 'tool';
  const body = out.text ? prettyIfJson(out.text) : '';
  const long = body.length > COLLAPSE_CHARS;
  const shown = expanded || !long ? body : body.slice(0, COLLAPSE_CHARS).trimEnd() + ' …';
  return (
    <div className="border border-border rounded p-2.5 bg-surface">
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <span
          className={cn(
            'font-mono text-[11px] font-semibold',
            isTool ? 'text-signal-ok' : 'text-accent',
          )}
        >
          {isTool ? '↳ ' : ''}{out.agent_name}
        </span>
        {isTool && <span className="font-mono text-[10px] text-fg-400">result</span>}
        {(out.function_calls || []).map((fc, i) => (
          <span key={i} className="font-mono text-[10px] text-fg-300 border border-border rounded px-1">
            → {fc}()
          </span>
        ))}
      </div>
      {body && (
        <pre className="font-mono text-[11px] text-fg-200 whitespace-pre-wrap break-words leading-relaxed">
          {shown}
        </pre>
      )}
      {long && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="font-mono text-[10px] text-accent hover:text-accent-hover mt-1"
        >
          {expanded ? '▲ show less' : '▼ show more'}
        </button>
      )}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function Lab() {
  const { workspaceId } = useWorkspace();
  const { user } = useAuth();
  const notif = useWorkspaceNotifications(workspaceId);

  // Latch the active run id: the consumer clears active_run_id at `done`, but the
  // agent_status/{runId} doc persists with its final state — so keep showing it.
  const [runId, setRunId] = useState<string | null>(null);
  useEffect(() => {
    if (notif?.active_run_id) setRunId(notif.active_run_id);
  }, [notif?.active_run_id]);

  const status = useAgentStatusRealtime(runId);
  const outputs = useAgentOutputsRealtime(runId);
  const steps = useAgentStepsRealtime(runId);

  const terminal = isTerminal(status?.status);

  // Names actually observed — from the RELIABLE append-only sources (the steps log + outputs),
  // not the lossy single status doc whose rapid overwrites get coalesced by onSnapshot.
  const observed = useMemo(() => {
    const s = new Set<string>();
    steps.forEach((st) => st.step && s.add(st.step));
    outputs.forEach((o) => o.agent_name && s.add(o.agent_name));
    return s;
  }, [steps, outputs]);

  // Active play(s) = every play-root or play-unique node seen in the log (never the shared
  // `researcher`, which would reveal the wrong subtree). The worker can run more than one play
  // (e.g. support + a risk co-play), so collect ALL and render them as sibling subtrees.
  const activePlays = useMemo(() => {
    const found = new Set<string>();
    for (const name of observed) {
      if (isPlayRoot(name)) found.add(name);
      else {
        const p = playForStep(name);
        if (p) found.add(p);
      }
    }
    return Object.keys(PLAYS).filter((k) => found.has(k)); // stable order
  }, [observed]);

  // Current (live) node = most recent real step, unless the run is terminal.
  const current = useMemo(() => {
    if (terminal) return null;
    for (let i = steps.length - 1; i >= 0; i--) {
      const s = steps[i].step;
      if (s && s !== 'done' && s !== 'claimed' && s !== 'error') return s;
    }
    return null;
  }, [steps, terminal]);

  // Monotonic progress: high-water mark over the reliable step log (+ live doc), 100 when done.
  const pct = useMemo(() => {
    let m = status?.progress_pct ?? 0;
    for (const st of steps) if (typeof st.progress_pct === 'number') m = Math.max(m, st.progress_pct);
    return terminal ? 100 : m;
  }, [steps, status?.progress_pct, terminal]);

  const stateFor = useCallback(
    (id: string): NodeState => {
      if (id === current) return 'active';
      if (observed.has(id)) return 'done';
      return 'pending';
    },
    [current, observed],
  );

  // Build the rendered tree: worker head → play slot(s) → worker tail.
  const tree: DagNode = useMemo(() => {
    const slots: DagNode[] = activePlays.length
      ? activePlays.map((p) => PLAYS[p])
      : [{ id: '__play_slot__', label: 'play (awaiting classification…)' }];
    const worker = WORKER_HEAD[0];
    const headChildren = WORKER_HEAD.slice(1);
    return {
      ...worker,
      children: [...headChildren, ...slots, ...WORKER_TAIL],
    };
  }, [activePlays]);

  // ─── trigger ───
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (scenario: Scenario) => {
      if (!user) {
        setError('Not signed in.');
        return;
      }
      setBusy(true);
      setError(null);
      // Clear the board for the new run; active_run_id will arrive via notifications.
      // (seen/activePlay/progress are all derived from the per-run steps/outputs hooks, which
      // reset automatically when runId changes — nothing else to clear.)
      setRunId(null);
      try {
        const token = await user.getIdToken();
        const res = await fetch(`${PYTHON_URL}/agents/orchestrator/demo-agent`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ scenario, workspace_id: workspaceId }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          setError(body?.error?.message || `Trigger failed (${res.status})`);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [user, workspaceId],
  );

  // ─── seed demo workspace ───
  // Workspace picker is sourced from the user's memberships (same shape the backend
  // uses to resolve a workspace). Lets us target a throwaway demo workspace instead of
  // always wiping the current one.
  const { data: userData } = useGetUserById(
    { userId: user?.uid || '' },
    { enabled: !!user?.uid },
  );
  const workspaces = useMemo(() => {
    const ms = userData?.users?.[0]?.workspaceMembers_on_user || [];
    return ms.map((m) => ({
      id: m.workspace.id,
      name: m.workspace.name || m.workspace.slug || m.workspace.id,
    }));
  }, [userData]);

  const [targetWs, setTargetWs] = useState<string>('');
  useEffect(() => {
    if (targetWs) return;
    if (workspaceId) setTargetWs(workspaceId);
    else if (workspaces.length) setTargetWs(workspaces[0].id);
  }, [workspaceId, workspaces, targetWs]);

  const [profile, setProfile] = useState<SeedProfile>('full');
  const [seedBusy, setSeedBusy] = useState(false);
  const [seedMsg, setSeedMsg] = useState<string | null>(null);

  // Read-only count: how many customers the chosen workspace holds, and how many are
  // demo accounts (matched by fixture slug). Refreshes on workspace switch + after seed.
  const [wsInfo, setWsInfo] = useState<{ customers_total: number; demo_customers: number; demo_expected: number } | null>(null);
  const inspect = useCallback(async (wsId: string) => {
    if (!user || !wsId) { setWsInfo(null); return; }
    try {
      const token = await user.getIdToken();
      const res = await fetch(
        `${PYTHON_URL}/agents/orchestrator/seed-workspace/inspect?workspace_id=${encodeURIComponent(wsId)}`,
        { headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } },
      );
      setWsInfo(res.ok ? await res.json() : null);
    } catch {
      setWsInfo(null);
    }
  }, [user]);
  useEffect(() => { void inspect(targetWs); }, [targetWs, inspect]);

  const seed = useCallback(async () => {
    if (!user) { setSeedMsg('Not signed in.'); return; }
    if (!targetWs) { setSeedMsg('Pick a workspace.'); return; }
    const wsName = workspaces.find((w) => w.id === targetWs)?.name || targetWs;
    const ok = window.confirm(
      `Seed the Northcrest demo into "${wsName}"?\n\n` +
      `This WIPES every customer, thread, need, and meeting in that workspace, then seeds ` +
      `the ${profile} demo set. Don't run this on a real client workspace.`,
    );
    if (!ok) return;
    setSeedBusy(true);
    setSeedMsg('Seeding… (reset + ~13 accounts; takes a few seconds)');
    try {
      const token = await user.getIdToken();
      const res = await fetch(`${PYTHON_URL}/agents/orchestrator/seed-workspace`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ workspace_id: targetWs, profile, reset: true }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setSeedMsg(body?.error?.message || `Seed failed (${res.status})`);
        return;
      }
      const counts = body?.counts || {};
      const summary = Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(', ');
      const errCount = (body?.errors || []).length;
      setSeedMsg(
        `Seeded: ${summary || 'nothing'}` +
        (errCount ? ` · ⚠ ${errCount} errors (see backend log)` : '') +
        '. Run sweep+drain (Pipeline page /app/dev/pipeline) to fire Quietfield going-dark.',
      );
      void inspect(targetWs);
    } catch (e) {
      setSeedMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSeedBusy(false);
    }
  }, [user, targetWs, profile, workspaces, inspect]);

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-4">
        <h1 className="font-display text-2xl tracking-wide text-fg-100">THE LAB</h1>
        <p className="font-mono text-xs text-fg-400">
          Watch the autonomous worker investigate, decide, and dispatch a play — live.
        </p>
      </div>

      {/* seed demo workspace */}
      <div className="border border-border rounded p-3 mb-5 bg-surface-2">
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono text-xs text-fg-200 uppercase tracking-wide">Seed demo data</span>
          <span className="font-mono text-[10px] text-fg-400">wipes + reseeds the chosen workspace</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={targetWs}
            onChange={(e) => setTargetWs(e.target.value)}
            disabled={seedBusy}
            className="font-mono text-xs px-2 py-1.5 border border-border rounded bg-surface text-fg-200"
          >
            {workspaces.length === 0 && <option value="">(no workspaces)</option>}
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name} · {w.id.slice(0, 8)}…{w.id === workspaceId ? ' (current)' : ''}
              </option>
            ))}
          </select>
          <select
            value={profile}
            onChange={(e) => setProfile(e.target.value as SeedProfile)}
            disabled={seedBusy}
            title="full = all 13 · lane1 = fresh handoffs · lane2 = established portfolio"
            className="font-mono text-xs px-2 py-1.5 border border-border rounded bg-surface text-fg-200"
          >
            {SEED_PROFILES.map((p) => (
              <option key={p.key} value={p.key}>{p.label}</option>
            ))}
          </select>
          <button
            onClick={seed}
            disabled={seedBusy || !targetWs}
            className={cn(
              'font-mono text-xs px-3 py-1.5 border border-accent rounded',
              'text-accent hover:text-accent-hover hover:border-accent-hover transition-colors',
              (seedBusy || !targetWs) && 'opacity-50 cursor-not-allowed',
            )}
          >
            {seedBusy ? 'Seeding…' : 'Seed Demo Workspace'}
          </button>
        </div>
        {wsInfo && (
          <p className="font-mono text-[10px] text-fg-400 mt-2">
            {wsInfo.customers_total} customers · {wsInfo.demo_customers}/{wsInfo.demo_expected} demo accounts present
          </p>
        )}
        {seedMsg && <p className="font-mono text-[11px] text-fg-300 mt-2 break-words">{seedMsg}</p>}
      </div>

      {/* triggers */}
      <div className="flex flex-wrap gap-2 mb-5">
        {SCENARIOS.map((s) => (
          <button
            key={s.key}
            onClick={() => run(s.key)}
            disabled={busy}
            title={s.hint}
            className={cn(
              'font-mono text-xs px-3 py-1.5 border border-border rounded',
              'text-fg-200 hover:border-accent hover:text-accent transition-colors',
              busy && 'opacity-50 cursor-not-allowed',
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="font-mono text-xs text-signal-risk mb-3">⚠ {error}</p>
      )}

      {/* live status header */}
      <div className="border border-border rounded p-4 bg-surface-2">
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono text-xs text-fg-200">
            {status?.customer_name || status?.customer_id || (runId ? 'run in progress' : 'idle')}
          </span>
          <span className={cn('font-mono text-xs uppercase tracking-wide', statusTone(status?.status))}>
            {status?.status || (runId ? 'starting…' : '—')}
          </span>
        </div>

        {/* progress bar */}
        <div className="h-1.5 w-full bg-surface rounded overflow-hidden mb-1">
          <div
            className={cn(
              'h-full transition-all duration-500',
              status?.status === 'failed' ? 'bg-signal-risk' : 'bg-accent',
            )}
            style={{ width: `${Math.max(0, Math.min(100, terminal ? 100 : pct))}%` }}
          />
        </div>
        <p className="font-mono text-[11px] text-fg-400 mb-4 h-4 truncate">
          {status?.message || (runId ? '…' : 'Pick a scenario to begin.')}
        </p>

        {/* trace DAG */}
        <div className="border-t border-border pt-3">
          <TraceNode node={tree} depth={0} stateFor={stateFor} />
        </div>

        {runId && (
          <p className="font-mono text-[10px] text-fg-400 mt-3">
            run {runId.slice(0, 8)}… · live from agent_status/{'{runId}'}
          </p>
        )}
      </div>

      {/* legend */}
      <div className="flex gap-4 mt-3 font-mono text-[10px] text-fg-400">
        <span><span className="text-signal-ok">●</span> done</span>
        <span><span className="text-accent">◆</span> running</span>
        <span><span className="text-fg-400">○</span> pending</span>
        <span>⟲ self-critique loop</span>
      </div>

      {/* outputs — what each agent / LLM actually produced */}
      <div className="mt-5">
        <h2 className="font-mono text-xs text-fg-300 uppercase tracking-wide mb-2">
          Agent output {outputs.length > 0 && <span className="text-fg-400">({outputs.length})</span>}
        </h2>
        {outputs.length === 0 ? (
          <p className="font-mono text-[11px] text-fg-400">
            {runId ? 'Waiting for the first model response…' : 'Run a scenario to see each step’s output.'}
          </p>
        ) : (
          <div className="space-y-2">
            {outputs.map((o) => (
              <OutputCard key={o.id} out={o} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
