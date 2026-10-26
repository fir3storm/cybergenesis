import { create } from 'zustand'
import type { ModelStatus, RunResult, Scenario, SimEvent, Twin, View } from '../types'

interface State {
  view: View
  twin: Twin | null
  scenarios: Scenario[]
  scenarioId: string
  selectedAsset: string | null
  runId: string | null
  runState: string
  events: SimEvent[]
  results: RunResult | null
  modelStatus: ModelStatus | null
  error: string | null
  viewMode: '3d' | '2d'
  set: (p: Partial<State>) => void
}

export const useStore = create<State>((set) => ({
  view: 'welcome',
  twin: null,
  scenarios: [],
  scenarioId: 'ransomware_activity',
  selectedAsset: null,
  runId: null,
  runState: 'IDLE',
  events: [],
  results: null,
  modelStatus: null,
  error: null,
  viewMode: '3d',
  set: (p) => set(p),
}))
