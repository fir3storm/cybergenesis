export interface Asset {
  id: string; name: string; asset_type: string; zone: string; posture: number;
  status: string; isolated: boolean; service_disabled: boolean;
  vulnerabilities: string[]; connected: string[]; pos: [number, number, number];
}
export interface Conn { source: string; target: string; trust: string; traversable: boolean; types: string[]; active: boolean; dir_forward_active?: boolean; dir_reverse_active?: boolean; one_way_blocked?: boolean }
export interface TwinDevice { asset_id: string; device_id: string | null; model: string; vendor: string; ports: string[]; links: { peer: string; state: string }[]; config_hash: string }
export interface Twin { assets: Asset[]; connections: Conn[]; devices?: TwinDevice[]; identities: Record<string, { asset: string; session_active: boolean; compromised: boolean; credential_version: number }>; containment: string[] }
export interface Scenario { id: string; name: string; description: string; severity: string; source_asset: string; target_asset: string; invariant: string; objectives: string[]; max_rounds?: number | null }
export interface SimEvent { event_type: string; run_id?: string; agent?: string | null; asset_id?: string | null; message: string; payload?: Record<string, unknown>; seq?: number; timestamp?: string; twin?: Twin }
export interface RunResult {
  run: { id: string; scenario_id: string; seed: number; state: string; mode: string; error: string | null; metrics: Record<string, unknown> };
  usage?: { prompt_tokens: number; completion_tokens: number; calls: number; models: string[] };
  verification: { outcome: string; invariant: string; checks: { name: string; passed: boolean; detail: string }[]; metrics: Record<string, unknown> } | null;
  decisions: { agent: string; decision: string; justification: string; confidence: number; model: string; mode: string; asset_ids: string[]; data?: { claim_evidence?: { claim: string; evidence_refs: string[] }[] } }[];
  policy: { action_type: string; asset_id: string; approved: boolean; reasons: string[] }[];
  executions: { action_type: string; asset_id: string; success: boolean; transition: Record<string, unknown> }[];
}
export interface Certificate {
  version: number
  run_id: string
  scenario: { id: string; name?: string; source: string; target: string; invariant: string }
  seed: number
  mode: string
  config_hash_before: string
  config_hash_after: string
  min_cut_edges: number
  campaigns: { outcome: string; unreachable_proof: { target_reachable: boolean; visited: string[]; frontier: { from: string; to: string; blocking_rule: string }[] } }[]
  event_hash_chain: string
  events_count: number
  signature: string
}
export interface ForkSummary {
  outcome: string | null
  effectiveness_pct: number | null
  disrupted: number | null
  risk_after_pct: number | null
  users_affected: number | null
  rounds: number | null
  actions: string[]
}
export interface ForkResult {
  fork_id: string
  parent_run_id: string
  at_event: string
  candidate: string
  original: ForkSummary
  fork: ForkSummary
  delta: { verdict_changed: boolean; effectiveness_pct?: number; disrupted?: number; risk_after_pct?: number; users_affected?: number; rounds?: number }
  original_twin?: Twin
  fork_twin?: Twin
  original_timeline?: { seq: number; event_type: string; message: string }[]
  fork_timeline?: { seq: number; event_type: string; message: string }[]
}
export interface ModelStatus { configured: boolean; reachable: boolean; model: string; mode: string; detail: string; provider?: string; provider_label?: string; base_url?: string }
export interface ProviderInfo {
  id: string
  label: string
  short: string
  description: string
  base_url: string
  model: string
  model_placeholder: string
  key_hint: string
  configured: boolean
  active: boolean
}
export interface AgentMsg { id: string; from_agent: string; to_agent: string | null; kind: string; payload: Record<string, unknown>; evidence_refs: string[]; seq: number }

export type View = 'welcome' | 'twin' | 'experiment' | 'battle' | 'arena' | 'agents' | 'attackpath' | 'verification' | 'evidence' | 'settings' | 'designer' | 'playbook' | 'library' | 'benchmark' | 'scorecards'

export interface ArenaDecision {
  agent_role: string; justification: string; confidence: number; model_id: string;
  mode: string; timestamp: string; evidence_refs: string[]; fallback_reason?: string | null
}
export interface ArenaEvaluation {
  available: boolean; created_at?: string; seed?: number; limitations?: string; live_requested?: boolean;
  summary?: Record<string, {cases: number; blue_wins: number; mean_disrupted: number; mean_latency_ms: number; tokens: number; live_cases: number; fallbacks: number}>
}
export interface ArenaRound {
  twin_after?: Twin
  round: number
  selected_path_blocked?: boolean
  evidence_ref?: string
  red_path: string[] | null
  blue_candidate: string | null
  blue_actions: { action_type: string; asset_id: string }[]
  blue_chosen_by?: string | null
  red_chosen_by?: string | null
  policy_rejections: string[]
  disrupted: number | null
  target_reachable_after: boolean
  winner_so_far: string
}
export interface ArenaMatch {
  initial_twin?: Twin
  decisions?: ArenaDecision[]
  id: string
  scenario_id: string
  winner: string
  reason: string
  mode: string
  rounds_played: number
  rounds: ArenaRound[]
  target_reachable_final: boolean
  total_disrupted: number
  final_twin: Twin
  context_memory?: ArenaMemorySummary
  memory?: ArenaMemorySummary
  created_at?: string | null
}
export interface ArenaMemorySummary {
  matches: number
  blue_learned: number
  red_learned: number
  blue: Record<string, { plays: number; blocks: number; disrupted: number }>
  red: Record<string, { plays: number; reaches: number }>
}
export interface ArenaLeague {
  matches: number
  red_wins: number
  blue_wins: number
  by_scenario: { scenario_id: string; matches: number; red_wins: number; blue_wins: number }[]
}

export interface LibraryItem { id: string; label: string; description: string; params_contract?: string; default_posture?: number; default_zone?: string; mitre?: string; d3fend?: string }
export interface Library { asset_types: LibraryItem[]; attack_steps: LibraryItem[]; defense_actions: LibraryItem[]; verification_kinds: string[]; zones: string[] }
export interface CustomTwinDef { id: string; name: string; description: string; assets: { id: string; name: string; asset_type: string; zone: string; posture?: number; pos: number[]; vulnerabilities?: string[] }[]; connections: { source: string; target: string; trust?: string; traversable?: boolean; types?: string[] }[]; created_at: string }
export interface CustomScenarioDef { id: string; name: string; description: string; definition: Record<string, unknown>; created_at: string }
