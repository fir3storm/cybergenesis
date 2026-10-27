import type { CustomScenarioDef, CustomTwinDef, Library, ModelStatus, RunResult, Scenario, SimEvent, Twin } from '../types'

export const API = (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL ?? 'http://localhost:8000'
export const WS = API.replace('http', 'ws')

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) throw new Error(`${path} -> HTTP ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  health: () => j<{ status: string }>('/api/health'),
  modelStatus: () => j<ModelStatus>('/api/models/status'),
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
  approve: (id: string, approved: boolean) => j<{ recorded: boolean }>(`/api/experiments/${id}/approve`, { method: 'POST', body: JSON.stringify({ approved }) }),
  fromText: (prompt_text: string, name: string) => j<CustomScenarioDef>('/api/scenarios/from-text', { method: 'POST', body: JSON.stringify({ prompt_text, name }) }),
}
