/**
 * Static node graph for the orchestrator worker, used by the Lab page to render a
 * live trace DAG. Node `id`s match the `current_step` value streamed to Firestore
 * (`agent_status/{runId}.current_step`) by the orchestrator's agent callbacks and
 * direct `stream_status` calls — see backend/orchestrator/runtime/callbacks.py and
 * worker/agent.py. Lighting a node up = "its name appeared in the stream".
 *
 * The play that runs is decided at runtime by classification, so the worker shows a
 * single "play slot": reveal whichever play's subtree once one of its node ids first
 * appears in the stream (`playForStep`).
 */

export interface DagNode {
  id: string;          // === current_step
  label: string;
  children?: DagNode[];
  loop?: boolean;      // render a ⟲ marker (LoopAgent: plan→critic→gate, may repeat)
}

// ─── Plays (dispatched as AgentTools under the worker) ───────────────────────

export const RISK_SAVE_PLAY: DagNode = {
  id: 'risk_save_play',
  label: 'risk_save_play',
  children: [
    { id: 'load_risk_context', label: 'load_risk_context' },
    { id: 'researcher', label: 'researcher' },
    {
      id: 'plan_critic',
      label: 'plan_critic',
      loop: true,
      children: [
        { id: 'risk_strategist', label: 'risk_strategist' },
        { id: 'critic', label: 'critic' },
        { id: 'critic_gate', label: 'critic_gate' },
      ],
    },
    { id: 'persist_risk_play', label: 'persist_risk_play' },
    { id: 'surface_risk_need', label: 'surface_risk_need' },
  ],
};

export const SUPPORT_PLAY: DagNode = {
  id: 'support_play',
  label: 'support_play',
  children: [
    { id: 'researcher', label: 'researcher' },
    { id: 'technical_triage', label: 'technical_triage' },
    { id: 'support_responder', label: 'support_responder' },
    { id: 'persist_support_reply', label: 'persist_support_reply' },
  ],
};

export const MEETING_BRIEF_PLAY: DagNode = {
  id: 'meeting_brief_play',
  label: 'meeting_brief_play',
  children: [
    { id: 'researcher', label: 'researcher' },
    { id: 'meeting_writer', label: 'meeting_writer' },
    { id: 'persist_meeting_brief', label: 'persist_meeting_brief' },
    { id: 'surface_meeting_need', label: 'surface_meeting_need' },
  ],
};

export const PLAYS: Record<string, DagNode> = {
  risk_save_play: RISK_SAVE_PLAY,
  support_play: SUPPORT_PLAY,
  meeting_brief_play: MEETING_BRIEF_PLAY,
};

// ─── Worker scaffold (always present) ────────────────────────────────────────

/** Worker-level nodes shown before/around the play slot, in run order. */
export const WORKER_HEAD: DagNode[] = [
  { id: 'orchestrator_worker', label: 'orchestrator_worker' },
  { id: 'investigate_account', label: 'investigate_account' },
];

/** Worker-level nodes after the play (memory consolidation tail). */
export const WORKER_TAIL: DagNode[] = [
  { id: 'consolidate_memory', label: 'consolidate_memory' },
];

// ─── Step → play resolution (reveal the right subtree) ───────────────────────

// Nodes that appear in MORE THAN ONE play (e.g. `researcher`) can't identify a play and must
// never set the active play — otherwise a meeting run would reveal the risk subtree just because
// both contain a researcher. Built by counting node occurrences across plays.
const _PLAY_COUNT: Record<string, number> = {};
const STEP_TO_PLAY: Record<string, string> = (() => {
  for (const play of Object.values(PLAYS)) {
    const walk = (n: DagNode) => {
      _PLAY_COUNT[n.id] = (_PLAY_COUNT[n.id] || 0) + 1;
      n.children?.forEach(walk);
    };
    walk(play);
  }
  const map: Record<string, string> = {};
  for (const [playId, play] of Object.entries(PLAYS)) {
    const walk = (n: DagNode) => {
      if (_PLAY_COUNT[n.id] === 1) map[n.id] = playId; // play-unique (incl. play root) only
      n.children?.forEach(walk);
    };
    walk(play);
  }
  return map;
})();

/** Which play a step uniquely belongs to, or null for shared/unknown nodes (e.g. `researcher`).
 *  Play roots and play-unique children resolve; ambiguous shared nodes never pick a play. */
export function playForStep(step: string | null | undefined): string | null {
  if (!step) return null;
  return STEP_TO_PLAY[step] ?? null;
}

/** True when `step` is one of the three play roots. */
export function isPlayRoot(step: string | null | undefined): boolean {
  return !!step && step in PLAYS;
}

export type NodeState = 'pending' | 'active' | 'done';
