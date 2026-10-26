import type { ModelStatus, RunResult, Scenario, SimEvent, Twin } from '../types'

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
  runExperiment: (id: string) => j<{ started: boolean }>(`/api/experiments/${id}/run`, { method: 'POST' }),
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
}
