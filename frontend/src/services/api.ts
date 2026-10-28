import type { ArenaEvaluation, ArenaLeague, ArenaMatch, ArenaMemorySummary, Certificate, ForkResult, CustomScenarioDef, CustomTwinDef, Library, ModelStatus, ProviderInfo, RunResult, Scenario, SimEvent, Twin } from '../types'

export const API = (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL ?? 'http://localhost:8000'
export const WS = API.replace('http', 'ws')

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: _authHeaders(), ...init })
  if (!r.ok) throw new Error(`${path} -> HTTP ${r.status}`)
  return r.json() as Promise<T>
}

function _authHeaders(): HeadersInit {
  // The admin token is either provided by the backend (when ADMIN_TOKEN env var is NOT set)
  // or must be read from the environment by the frontend (when ADMIN_TOKEN IS set).
  // We store it in sessionStorage after the first successful /api/settings/providers call.
  const envToken = (import.meta as unknown as { env: Record<string, string> }).env.VITE_ADMIN_TOKEN
  try {
    const t = envToken || sessionStorage.getItem('cybergenesis_admin_token')
    return t ? { 'x-admin-token': t, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }
  } catch {
    return envToken ? { 'x-admin-token': envToken, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }
  }
}

export const api = {
  health: () => j<{ status: string }>('/api/health'),
  modelStatus: () => j<ModelStatus>('/api/models/status'),
  providers: () => j<{ providers: ProviderInfo[]; active: string; admin_token?: string }>('/api/settings/providers'),
  activateProvider: (provider: string, api_key: string, model: string, base_url: string) =>
    j<ModelStatus & { active: string }>('/api/settings/provider', { method: 'POST', body: JSON.stringify({ provider, api_key: api_key || null, model, base_url: base_url || null }), headers: _authHeaders() }),
  twin: () => j<Twin>('/api/twin'),
  reset: () => j<{ twin: Twin }>('/api/twin/reset', { method: 'POST' }),
  scenarios: () => j<Scenario[]>('/api/scenarios'),
  createExperiment: (scenario_id: string, seed = 42) =>
    j<{ id: string }>('/api/experiments', { method: 'POST', body: JSON.stringify({ scenario_id, seed }) }),
  runExperiment: (id: string, stepDelayMs?: number) => j<{ started: boolean }>(`/api/experiments/${id}/run${stepDelayMs !== undefined ? `?step_delay_ms=${stepDelayMs}` : ''}`, { method: 'POST' }),
  snapshots: (id: string) => j<{ label: string; snapshot: { status: Record<string, string> } }[]>(`/api/experiments/${id}/snapshots`),
  fromImage: (image_data_url: string, name: string) => j<CustomTwinDef>('/api/twins/from-image', { method: 'POST', body: JSON.stringify({ image_data_url, name }) }),
  results: (id: string) => j<RunResult>(`/api/experiments/${id}/results`),
  events: (id: string) => j<SimEvent[]>(`/api/experiments/${id}/events`),
  evidence: (id: string) => j<{ id: string; kind: string; ref: string; summary: string }[]>(`/api/experiments/${id}/evidence`),
  report: (id: string) => j<Record<string, unknown>>(`/api/experiments/${id}/report`),
  reportMarkdown: async (id: string): Promise<string> => {
    const r = await fetch(`${API}/api/experiments/${id}/report/markdown`)
    if (!r.ok) throw new Error(`report/markdown -> HTTP ${r.status}`)
    return r.text()
  },
  experiments: () => j<{ id: string; scenario_id: string; state: string; mode: string; created_at: string }[]>('/api/experiments'),
  devices: (params: string) => j<{ total: number; items: { id: string; vendor: string; model: string; category: string; tier: string; os: { name: string } }[] }>(`/api/devices/catalog?${params}`),
  device: (id: string) => j<{ id: string; vendor: string; model: string; category: string; tier: string; personality: { cli: string; gui: string }; hardware: { ports: { prefix: string; start: number; count: number; speed: string; media: string }[] } }>(`/api/devices/catalog/${id}`),
  twinAction: (action_type: string, asset_id: string, params: Record<string, unknown>) =>
    j<{ approved: boolean }>(`/api/twin/action`, { method: 'POST', body: JSON.stringify({ action_type, asset_id, params }) }),
  deviceConfig: (assetId: string) => j<{ config: Record<string, unknown>; config_hash: string }>(`/api/twin/devices/${assetId}/config`),
  stageDiff: (assetId: string, diff: unknown) => j<{ staged: boolean }>(`/api/twin/devices/${assetId}/config/diff`, { method: 'POST', body: JSON.stringify({ diff }) }),
  previewDiff: (assetId: string, diff: unknown) => j<{ changes: { src: string; dst: string; before_reachable: boolean; after_reachable: boolean }[] }>(`/api/twin/devices/${assetId}/config/preview`, { method: 'POST', body: JSON.stringify({ diff }) }),
  commitDiff: (assetId: string) => j<{ committed: boolean; twin: Twin }>(`/api/twin/devices/${assetId}/config/commit`, { method: 'POST' }),
  cliExec: (assetId: string, input: string) => j<{ output: string; dialect: string }>(`/api/cli/${assetId}/exec`, { method: 'POST', body: JSON.stringify({ input }) }),
  osState: (assetId: string) => j<{ status: string; processes: { name: string; pid: number; suspicious: boolean }[]; events: { type: string; message: string }[]; services: { name: string; enabled: boolean }[]; users: { name: string; role: string; mfa: boolean }[]; files: string[] }>(`/api/twin/devices/${assetId}/os`),
  auditRun: () => j<{ findings: { device: string; weakness: string; severity: string; evidence: string; fix_diff: Record<string, unknown> }[] }>('/api/audit/run', { method: 'POST' }),
  explainConfig: (text: string) => j<{ explanation: string; mode: string }>('/api/config/explain', { method: 'POST', body: JSON.stringify({ text }) }),
  drift: () => j<{ drift: { asset_id: string; field: string; committed: unknown; current: unknown; risky: boolean }[] }>('/api/twin/drift'),
  library: () => j<Library>('/api/library'),
  benchmark: () => j<{ available: boolean; pairs?: number; scope?: string; detail?: string; calibration?: { runs_scored: number; mean_confidence_pass: number | null; mean_confidence_fail: number | null; note?: string }; summary?: Record<string, { pass_rate_pct: number; mean_effectiveness_pct: number; mean_optimality_gap: number; mean_disrupted: number }> }>('/api/benchmark'),
  customTwins: () => j<CustomTwinDef[]>('/api/twins/custom'),
  createCustomTwin: (body: unknown) => j<CustomTwinDef>('/api/twins/custom', { method: 'POST', body: JSON.stringify(body) }),
  deleteCustomTwin: (id: string) => j<{ deleted: boolean }>(`/api/twins/custom/${id}`, { method: 'DELETE' }),
  activateCustomTwin: (id: string) => j<{ twin: Twin }>(`/api/twins/custom/${id}/activate`, { method: 'POST' }),
  activateBuiltinTwin: () => j<{ twin: Twin }>('/api/twins/builtin/activate', { method: 'POST' }),
  customScenarios: () => j<CustomScenarioDef[]>('/api/scenarios/custom'),
  createCustomScenario: (body: unknown) => j<CustomScenarioDef>('/api/scenarios/custom', { method: 'POST', body: JSON.stringify(body) }),
  deleteCustomScenario: (id: string) => j<{ deleted: boolean }>(`/api/scenarios/custom/${id}`, { method: 'DELETE' }),
  createCustomExperiment: (body: unknown) => j<{ id: string }>('/api/experiments/custom', { method: 'POST', body: JSON.stringify(body) }),
  agents: () => j<{ id: string; name: string; team: string; engine: string; description: string; tools: string[]; can_propose_actions: string[]; prompt_version: string; prompt_hash: string; scorecard: { runs: number; last_mode: string | null; last_confidence: number | null } }[]>('/api/agents'),
  messages: (runId: string) => j<{ id: string; from_agent: string; to_agent: string | null; kind: string; payload: Record<string, unknown>; evidence_refs: string[]; seq: number }[]>(`/api/experiments/${runId}/messages`),
  agentDetail: (id: string) => j<{ duties: string[]; input_model: string; output_model: string; timeout_s: number; max_tokens: number }>(`/api/agents/${id}`),
  approve: (id: string, approved: boolean) => j<{ recorded: boolean }>(`/api/experiments/${id}/approve`, { method: 'POST', body: JSON.stringify({ approved }) }),
  deny: (id: string) => j<{ recorded: boolean }>(`/api/experiments/${id}/deny`, { method: 'POST' }),
  benchmarkRun: (n: number, seed: number) => j<{ run_id: string }>('/api/benchmark/run', { method: 'POST', body: JSON.stringify({ n, seed, mode: 'offline' }) }),
  benchmarkStatus: (id: string) => j<{ state: string; done: number; total: number }>(`/api/benchmark/run/${id}`),
  evalRun: (n: number, seed: number, mode: string) => j<{ run_id: string }>('/api/agents/eval/run', { method: 'POST', body: JSON.stringify({ n, seed, mode }) }),
  evalStatus: (id: string) => j<{ state: string; done: number; total: number; result?: unknown }>(`/api/agents/eval/run/${id}`),
  evalLatest: () => j<{ available: boolean; result?: { n: number; mode: string; agents: Record<string, Record<string, unknown>>; calibration: Record<string, { bucket: string; n: number; accuracy: number | null }[]> } }>('/api/agents/eval/latest'),
  learningCurve: () => j<{ points: { run_id: string; scenario_id: string; mode: string; outcome: string; optimality_gap: number | null }[]; runs: number }>('/api/learning/curve'),
  calibration: () => j<{ buckets: { bucket: string; n: number; passes: number; pass_rate_pct: number | null }[] }>('/api/benchmark/calibration'),
  getCertificate: (id: string) => j<Certificate>(`/api/experiments/${id}/certificate`),
  certificate: (id: string) => j<Certificate>(`/api/experiments/${id}/certificate`),
  fork: (id: string, choose_candidate: number | string, at_event = 'attacked') =>
    j<ForkResult>(`/api/experiments/${id}/fork`, { method: 'POST', body: JSON.stringify({ choose_candidate, at_event }) }),
  approvalStatus: (id: string) => j<{ pending: boolean; label?: string; disrupted?: number; expires_in_s?: number; mobile_url?: string }>(`/api/experiments/${id}/approval`),
  fromText: (prompt_text: string, name: string) => j<CustomScenarioDef>('/api/scenarios/from-text', { method: 'POST', body: JSON.stringify({ prompt_text, name }) }),
  arenaPlay: (scenario_id: string, mode: string, max_rounds?: number) =>
    j<ArenaMatch>('/api/arena/matches', { method: 'POST', body: JSON.stringify({ scenario_id, mode, max_rounds: max_rounds ?? null }) }),
  arenaMatches: () => j<{ id: string; scenario_id: string; winner: string; mode: string; rounds_played: number }[]>('/api/arena/matches'),
  arenaMatch: (id: string) => j<ArenaMatch>(`/api/arena/matches/${id}`),
  arenaMemory: () => j<ArenaMemorySummary>('/api/arena/memory'),
  arenaEvaluation: () => j<ArenaEvaluation>('/api/arena/evaluation'),
  arenaLeague: () => j<ArenaLeague>('/api/arena/league'),
  arenaCertificate: (id: string) => j<Record<string, unknown>>(`/api/arena/matches/${id}/certificate`),
}
