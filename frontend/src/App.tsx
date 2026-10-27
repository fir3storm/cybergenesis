import { Component, Suspense, lazy, useEffect, useRef, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  Activity, Bot, Boxes, Bug, Cpu, Database, Download, FlaskConical, Folder, Globe, KeyRound, MessageSquareText, Monitor, PenTool, Play, Radar, RotateCcw, Route,
  Settings as SettingsIcon, Server, Share2, Shield, ShieldCheck, Siren, Swords, Home, Network, FileText,
} from 'lucide-react'

export const ASSET_TYPE_ICON: Record<string, ReactNode> = {
  gateway: <Globe size={12} className="inline" />, firewall: <Shield size={12} className="inline" />,
  web_server: <Server size={12} className="inline" />, app_server: <Cpu size={12} className="inline" />,
  database: <Database size={12} className="inline" />, identity: <KeyRound size={12} className="inline" />,
  workstation: <Monitor size={12} className="inline" />, file_server: <Folder size={12} className="inline" />,
  sensor: <Radar size={12} className="inline" />,
}
import { ATTACK_PATHS, STATUS_COLOR } from './components/status'

const TwinScene = lazy(() => import('./components/TwinScene'))
const TwinDesigner = lazy(() => import('./components/TwinDesigner'))
const AttackPlaybook = lazy(() => import('./components/AttackPlaybook'))
const ComponentLibrary = lazy(() => import('./components/ComponentLibrary'))
const SCENARIO_ICONS: Record<string, ReactNode> = {
  ransomware_activity: <Bug size={13} className="inline text-red-300" />,
  compromised_identity: <KeyRound size={13} className="inline text-amber-300" />,
  lateral_movement: <Route size={13} className="inline text-orange-300" />,
  data_exfiltration: <Share2 size={13} className="inline text-rose-300" />,
}
import { api, WS } from './services/api'
import { useStore } from './stores/store'
import type { Asset, Twin, View } from './types'

const AGENTS = [
  { id: 'observer', name: 'Observer', desc: 'Deterministic telemetry anomaly detection', engine: 'Deterministic', input: 'SimulationEvents (telemetry)', output: 'AgentObservation', duties: ['Consume synthetic telemetry', 'Detect anomaly patterns (file bursts, auth failures, network paths)', 'Emit structured observation with confidence'] },
  { id: 'adversary_simulator', name: 'Adversary Simulator', desc: 'Typed, bounded synthetic scenario actions', engine: 'Deterministic', input: 'Scenario definition (JSON)', output: 'AttackScenarioPlan + telemetry', duties: ['Execute predefined typed attack steps only', 'Mutate twin to attacked state', 'Never generates payloads or commands'] },
  { id: 'incident_investigator', name: 'Incident Investigator', desc: 'Meta Muse Spark evidence-grounded reasoning', engine: 'Meta Muse Spark (offline fallback labelled)', input: 'AgentObservation + telemetry + topology', output: 'IncidentHypothesis', duties: ['Correlate evidence across assets', 'Separate confirmed facts from speculation', 'Estimate threat level with confidence'] },
  { id: 'defense_strategist', name: 'Defense Strategist', desc: 'Meta Muse Spark countermeasure proposals', engine: 'Meta Muse Spark (offline fallback labelled)', input: 'IncidentHypothesis + live twin state', output: 'DefenseProposal', duties: ['Propose allowlisted countermeasures', 'Prefer least disruptive effective action', 'Retry once with policy feedback if rejected'] },
  { id: 'defense_executor', name: 'Defense Executor', desc: 'Deterministic policy gate + allowlisted execution', engine: 'Deterministic', input: 'DefenseProposal', output: 'PolicyDecision + DefenseExecutionResult', duties: ['Validate every action against the deterministic policy engine', 'Apply approved actions to the twin only', 'Record exact state transitions'] },
  { id: 'verification_scientist', name: 'Verification Scientist', desc: 'Independent replay & invariant checking', engine: 'Deterministic replay', input: 'Scenario + modified twin', output: 'VerificationResult (PASS/FAIL)', duties: ['Replay the identical attack objective', 'Compare before/after reachability or access', 'Compute effectiveness + operational cost'] },
]
const STAGES = ['SCENARIO_SELECTED', 'ATTACK_SIMULATING', 'TELEMETRY_COLLECTED', 'INVESTIGATING', 'DEFENSE_PROPOSED', 'POLICY_VALIDATING', 'DEFENSE_APPLYING', 'VERIFYING', 'COMPLETED']
const DEMO_CLOCK: Record<string, string> = {
  IDLE: '0:00', SCENARIO_SELECTED: '0:20', ATTACK_SIMULATING: '0:40', TELEMETRY_COLLECTED: '0:55',
  INVESTIGATING: '1:00', DEFENSE_PROPOSED: '1:30', POLICY_VALIDATING: '1:45', DEFENSE_APPLYING: '1:55',
  VERIFYING: '2:05', COMPLETED: '2:30', FAILED: '—',
}

class SceneBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

function Twin2D({ twin }: { twin: Twin }) {
  const { selectedAsset, set } = useStore()
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-2 p-3" role="list" aria-label="Infrastructure assets (2D view)">
      {twin.assets.map((a) => (
        <button key={a.id} role="listitem" onClick={() => set({ selectedAsset: a.id })}
          className={`text-left rounded-lg border p-3 bg-slate-900/70 ${selectedAsset === a.id ? 'border-cyan-300' : 'border-slate-700'}`}>
          <div className="text-xs font-mono" style={{ color: STATUS_COLOR[a.status] }}>{a.status.toUpperCase()}</div>
          <div className="text-sm font-semibold">{a.name}</div>
          <div className="text-[11px] text-slate-400">{a.zone} · posture {(a.posture * 100).toFixed(0)}%</div>
        </button>
      ))}
    </div>
  )
}

export function SkeletonTwin() {
  return (
    <div className="grid h-full grid-cols-3 gap-3 p-4" aria-label="Loading 3D twin" role="status">
      {Array.from({ length: 9 }, (_, i) => <div key={i} className="skeleton min-h-16" />)}
    </div>
  )
}

function TwinView({ twin }: { twin: Twin }) {
  return (
    <SceneBoundary fallback={<div><p className="p-3 text-amber-300 text-sm">3D unavailable (WebGL) — 2D fallback shown. All functions remain available.</p><Twin2D twin={twin} /></div>}>
      <Suspense fallback={<SkeletonTwin />}>
        <TwinScene twin={twin} />
      </Suspense>
    </SceneBoundary>
  )
}

interface Candidate { label: string; origin: string; blocked: boolean; disrupted: number | null; feasible: boolean; detail: string }
interface Round { round: number; path: string[] | null; effectiveness_pct: number; outcome: string; red_team_mode: string | null }

export function CandidatesPanel() {
  const s = useStore()
  const cands = (s.results?.verification?.metrics.candidates as Candidate[] | undefined) ?? []
  const m = s.results?.verification?.metrics
  if (!cands.length) return null
  return (
    <section className="rounded-xl border border-slate-800 glass-panel p-3">
      <h2 className="mb-2 text-xs font-bold tracking-wider text-cyan-300">SIMULATE-BEFORE-ACTING · CANDIDATES</h2>
      {cands.map((c, i) => (
        <div key={i} className={`mb-1 rounded px-2 py-1.5 text-xs ${i === 0 ? 'bg-emerald-950/50 border border-emerald-800' : 'bg-slate-950/60'}`}>
          <span className={c.blocked ? 'text-emerald-300' : 'text-red-300'}>{c.blocked ? '✓ blocks' : '✗ fails'}</span>{' '}
          <b>{c.label}</b> <span className="text-slate-500">[{c.origin}]</span>
          <span className="text-slate-400"> · disruption: {c.disrupted ?? '—'}</span>
          {i === 0 && <span className="ml-1 rounded bg-emerald-600 px-1 text-[9px] font-bold text-slate-950">SELECTED</span>}
        </div>
      ))}
      {m && <p className="mt-1 font-mono text-[10px] text-slate-400">
        Optimality: NetworkX min edge cut = {String(m.optimal_edge_cut ?? '—')} · defense removed {String(m.defense_edges_removed ?? '—')} edges · gap = {String(m.optimality_gap ?? '—')}
      </p>}
    </section>
  )
}

export function ResilienceCurve() {
  const s = useStore()
  const rounds = (s.results?.verification?.metrics.rounds as Round[] | undefined) ?? []
  if (!rounds.length) return null
  const pts = rounds.map((r, i) => `${30 + i * 90},${90 - (r.effectiveness_pct / 100) * 70}`).join(' ')
  return (
    <section className="mt-4 rounded-xl border border-slate-800 glass-panel p-4">
      <h2 className="font-bold text-cyan-200">Resilience Curve — Red Team Rounds</h2>
      <svg viewBox={`0 0 ${60 + rounds.length * 90} 110`} className="mt-2 w-full max-w-md" role="img" aria-label="Resilience curve over red-team rounds">
        <line x1={25} y1={15} x2={25} y2={92} stroke="#334155" /><line x1={25} y1={92} x2={55 + rounds.length * 90} y2={92} stroke="#334155" />
        <polyline points={pts} fill="none" stroke="#34d399" strokeWidth={2.5} />
        {rounds.map((r, i) => <g key={r.round}><circle cx={30 + i * 90} cy={90 - (r.effectiveness_pct / 100) * 70} r={5} fill={r.outcome === 'PASS' ? '#34d399' : '#ef4444'} />
          <text x={30 + i * 90} y={106} textAnchor="middle" fill="#94a3b8" fontSize={9}>R{r.round} · {r.effectiveness_pct}%</text></g>)}
      </svg>
      {rounds.map((r) => <p key={r.round} className="text-xs text-slate-300">Round {r.round}: {r.path ? r.path.join(' → ') : 'initial attack'} → {r.outcome} <span className="text-slate-500">({r.effectiveness_pct}% checks{r.red_team_mode ? `, red team ${r.red_team_mode}` : ''})</span></p>)}
    </section>
  )
}

/** Plain-language attack chain: reads left-to-right without needing the 3D view. */
function AttackChain() {
  const s = useStore()
  const path = ATTACK_PATHS[s.scenarioId] ?? []
  const byId = Object.fromEntries((s.twin?.assets ?? []).map((a) => [a.id, a]))
  const blocked = s.results?.verification?.metrics.after_reachable_or_granted === false
  if (!path.length) return null
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded-xl border border-red-900/50 glass-panel px-3 py-2" aria-label="Attack path in plain language">
      <span className="font-mono text-[10px] tracking-wider text-red-300">ATTACK PATH</span>
      {path.map((id, i) => {
        const a = byId[id]
        const role = i === 0 ? 'SOURCE' : i === path.length - 1 ? 'TARGET' : `PIVOT ${i}`
        return (
          <span key={id} className="flex items-center gap-1.5">
            {i > 0 && <span className={blocked && i === path.length - 1 ? 'text-emerald-300 font-bold' : 'text-red-400'}>{blocked && i === path.length - 1 ? '✕ blocked →' : '→'}</span>}
            <button onClick={() => s.set({ selectedAsset: id })} className="rounded-full border px-2 py-1 text-[11px]"
              style={{ borderColor: STATUS_COLOR[a?.status ?? 'healthy'], color: STATUS_COLOR[a?.status ?? 'healthy'] }}>
              <b>{i + 1}</b> {a?.name ?? id} <span className="opacity-70">· {role} · {(a?.status ?? '—').toUpperCase()}</span>
            </button>
          </span>
        )
      })}
      <span className={`ml-auto text-[11px] ${blocked ? 'text-emerald-300 font-bold' : 'text-slate-400'}`}>
        {s.results?.verification ? (blocked ? '✓ Defense cut this path (verified)' : '✗ Path still open (verification failed)') : 'Run an experiment to test this path'}
      </span>
    </div>
  )
}

function MapFocusToggle() {
  const s = useStore()
  return (
    <div className="flex items-center gap-1 text-[11px]">
      <span className="text-slate-500">Map:</span>
      <button onClick={() => s.set({ mapFocus: true })} className={`rounded-full border px-2 py-0.5 ${s.mapFocus ? 'border-red-400 bg-red-500/20 text-red-200' : 'border-slate-700 text-slate-400'}`}>Attack path only</button>
      <button onClick={() => s.set({ mapFocus: false })} className={`rounded-full border px-2 py-0.5 ${!s.mapFocus ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200' : 'border-slate-700 text-slate-400'}`}>Full topology</button>
    </div>
  )
}

function AssetPanel({ asset }: { asset: Asset }) {
  const twin = useStore((s) => s.twin)
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2"><Shield size={16} className="text-cyan-300" /><b>{asset.name}</b></div>
      <div>Status: <span style={{ color: STATUS_COLOR[asset.status] }}>{asset.status}</span></div>
      <div>Zone: {asset.zone} · Type: {asset.asset_type}</div>
      <div>Security posture: {(asset.posture * 100).toFixed(0)}%</div>
      <div>Isolated: {asset.isolated ? 'yes (contained)' : 'no'} · Service disabled: {asset.service_disabled ? 'yes' : 'no'}</div>
      <div>Simulated vulnerabilities: {asset.vulnerabilities.length ? asset.vulnerabilities.join(', ') : 'none'}</div>
      <div>Connected: {asset.connected.join(', ') || 'none'}</div>
      {twin && <div>Containment: {twin.containment.join(', ') || 'none active'}</div>}
    </div>
  )
}

export default function App() {
  const s = useStore()
  const [commentaryOn, setCommentaryOn] = useState(true)
  const [selectedAgent, setSelectedAgent] = useState('incident_investigator')
  const [speed, setSpeed] = useState(1)
  const [cinematic, setCinematic] = useState(false)
  const [replayIdx, setReplayIdx] = useState<number | null>(null)
  const [replayPlaying, setReplayPlaying] = useState(false)
  const [snapshots, setSnapshots] = useState<{ label: string; snapshot: { status: Record<string, string> } }[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const pollRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    api.twin().then((t) => s.set({ twin: t })).catch((e) => s.set({ error: `Backend unreachable: ${e.message}. Start backend on :8000.` }))
    api.scenarios().then((sc) => s.set({ scenarios: sc })).catch(() => undefined)
    api.modelStatus().then((m) => s.set({ modelStatus: m })).catch(() => s.set({ modelStatus: { configured: false, reachable: false, model: 'muse-spark-1.3', mode: 'offline', detail: 'status endpoint unreachable' } }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const stopPoll = () => { if (pollRef.current) window.clearInterval(pollRef.current) }

  async function refreshResults(id: string) {
    try {
      const r = await api.results(id)
      s.set({ results: r, runState: r.run.state })
      const t = await api.twin(); s.set({ twin: t })
      if (r.run.state === 'COMPLETED' || r.run.state === 'FAILED') {
        stopPoll()
        api.snapshots(id).then(setSnapshots).catch(() => undefined)
        const base = useStore.getState().replayBaseline
        if (base) {
          const evs = await api.events(id)
          const tele = evs.filter((e) => e.event_type === 'telemetry').map((e) => e.message)
          s.set({ replayVerdict: JSON.stringify(tele) === JSON.stringify(base)
            ? `Replay proof: telemetry identical to the previous run (${tele.length} events, same seed 42). Same seed → same result.`
            : `Replay proof: telemetry differs from the previous run (${tele.length} vs ${base.length} events) — investigate before trusting determinism.` })
        }
      }
    } catch { /* polling is best-effort; WS is primary */ }
  }

  async function runDemo(scenarioId = s.scenarioId, replay = false) {
    if (replay) {
      const tele = s.events.filter((e) => e.event_type === 'telemetry').map((e) => e.message)
      s.set({ replayBaseline: tele.length ? tele : null, replayVerdict: null })
    }
    s.set({ error: null, events: [], results: null, runState: 'SCENARIO_SELECTED', view: 'experiment', scenarioId })
    try {
      await api.reset()
      const created = await api.createExperiment(scenarioId, 42)
      s.set({ runId: created.id })
      await api.runExperiment(created.id, Math.round(350 / speed))
      wsRef.current?.close()
      const ws = new WebSocket(`${WS}/ws/experiments/${created.id}`)
      wsRef.current = ws
      ws.onmessage = (msg) => {
        const ev = JSON.parse(msg.data as string)
        useStore.setState((st) => ({ events: [...st.events.slice(-199), ev], twin: ev.twin ?? st.twin,
          runState: (ev.payload?.state as string) ?? st.runState }))
        if (ev.event_type === 'completed' || ev.event_type === 'failed') void refreshResults(created.id)
      }
      ws.onerror = () => s.set({ error: 'WebSocket disconnected — polling fallback active' })
      stopPoll()
      pollRef.current = window.setInterval(() => void refreshResults(created.id), 1500)
    } catch (e) {
      s.set({ error: `Experiment failed to start: ${(e as Error).message}`, runState: 'FAILED' })
    }
  }

  async function runCustomExperiment(customScenarioId: string, customTwinId: string | null) {
    s.set({ error: null, events: [], results: null, runState: 'SCENARIO_SELECTED', view: 'experiment', replayBaseline: null, replayVerdict: null })
    try {
      const created = await api.createCustomExperiment({ custom_scenario_id: customScenarioId, custom_twin_id: customTwinId, seed: 42 })
      s.set({ runId: created.id })
      await api.runExperiment(created.id, Math.round(350 / speed))
      wsRef.current?.close()
      const ws = new WebSocket(`${WS}/ws/experiments/${created.id}`)
      wsRef.current = ws
      ws.onmessage = (msg) => {
        const ev = JSON.parse(msg.data as string)
        useStore.setState((st) => ({ events: [...st.events.slice(-199), ev], twin: ev.twin ?? st.twin,
          runState: (ev.payload?.state as string) ?? st.runState }))
        if (ev.event_type === 'completed' || ev.event_type === 'failed') void refreshResults(created.id)
      }
      ws.onerror = () => s.set({ error: 'WebSocket disconnected — polling fallback active' })
      stopPoll()
      pollRef.current = window.setInterval(() => void refreshResults(created.id), 1500)
    } catch (e) {
      s.set({ error: `Custom experiment failed to start: ${(e as Error).message}`, runState: 'FAILED' })
    }
  }

  async function resetAll() {
    stopPoll(); wsRef.current?.close()
    try { const r = await api.reset(); s.set({ twin: r.twin, events: [], results: null, runState: 'IDLE', error: null }) }
    catch (e) { s.set({ error: (e as Error).message }) }
  }

  function downloadMarkdown() {
    if (!s.runId) return
    api.reportMarkdown(s.runId).then((md) => {
      const blob = new Blob([md], { type: 'text/markdown' })
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
      a.download = `cybergenesis-report-${s.runId}.md`; a.click()
    }).catch((e) => s.set({ error: (e as Error).message }))
  }

  function exportReport() {
    if (!s.runId) return
    api.report(s.runId).then((r) => {
      const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' })
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
      a.download = `cybergenesis-report-${s.runId}.json`; a.click()
    }).catch((e) => s.set({ error: (e as Error).message }))
  }

  // Replay player: step through the stored event timeline (attack -> defense -> proof)
  useEffect(() => {
    if (!replayPlaying) return
    const iv = window.setInterval(() => {
      setReplayIdx((cur) => {
        const next = (cur ?? -1) + 1
        if (next >= s.events.length) { setReplayPlaying(false); return cur }
        const ev = s.events[next]
        if (ev?.asset_id) s.set({ selectedAsset: ev.asset_id })
        return next
      })
    }, Math.round(650 / speed))
    return () => window.clearInterval(iv)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replayPlaying, s.events.length, speed])

  // Keyboard shortcuts: Space=run, R=reset, 1-4=select scenario (ignored while typing)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON') return
      if (e.key === 'Escape') { setCinematic(false); return }
      const st = useStore.getState()
      if (e.key === ' ') { e.preventDefault(); if (st.view === 'twin' || st.view === 'experiment') void runDemo(st.scenarioId) }
      else if (e.key.toLowerCase() === 'r') void resetAll()
      else if (['1', '2', '3', '4'].includes(e.key)) {
        const sc = st.scenarios[Number(e.key) - 1]
        if (sc) st.set({ scenarioId: sc.id })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const scenarioDef = s.scenarios.find((x) => x.id === s.scenarioId)
  const commentary = ((): string => {
    const scName = scenarioDef?.name ?? 'the selected scenario'
    const lastDecision = [...s.events].reverse().find((e) => e.event_type === 'agent_decision')
    switch (s.runState) {
      case 'IDLE': return 'Ready. Press Space (or Run) to introduce a synthetic incident into the twin. Everything is simulated and isolated.'
      case 'SCENARIO_SELECTED': return `Scenario selected: ${scName}. Saving a baseline snapshot so the defense can be measured against it.`
      case 'ATTACK_SIMULATING': return `Introducing synthetic ${scName.toLowerCase()} activity. Watch the red attack path — particles flow toward the target asset.`
      case 'TELEMETRY_COLLECTED': return `The Observer has collected the synthetic telemetry: ${lastDecision?.message ?? 'anomaly pattern matched against real twin state.'}`
      case 'INVESTIGATING': return `${s.modelStatus?.mode === 'live' ? 'Meta Muse Spark is investigating' : 'The Investigator (offline deterministic mode) is analysing'} the evidence — hypothesis, affected assets, confidence.`
      case 'DEFENSE_PROPOSED': return `Defense proposed: ${lastDecision?.message ?? 'countermeasure ready for policy review.'}`
      case 'POLICY_VALIDATING': return 'The deterministic policy engine — independent of the AI — checks the proposal against the allowlist and preconditions.'
      case 'DEFENSE_APPLYING': return 'Applying the approved simulated defense. Watch the node change state and gain a containment ring in the twin.'
      case 'VERIFYING': return 'The Verification Scientist now replays the identical attack against the modified twin. Same objective, same seed.'
      case 'COMPLETED': return s.results?.verification
        ? `Verification ${s.results.verification.outcome}: ${s.results.verification.invariant}. Effectiveness ${String(s.results.verification.metrics.defense_effectiveness_pct)}%, at a cost of ${String(s.results.verification.metrics.operational_impact_disrupted_legit_paths)} disrupted legitimate paths. That is computed proof, not a claim.`
        : 'Experiment complete. Open the Verification Lab for before/after proof.'
      case 'FAILED': return `Experiment failed honestly${s.results?.run.error ? `: ${s.results.run.error}` : ''}. No fake success — inspect the timeline and evidence.`
      default: return `Workflow stage: ${s.runState}.`
    }
  })()

  const selected = s.twin?.assets.find((a) => a.id === s.selectedAsset) ?? null
  const scenario = s.scenarios.find((x) => x.id === s.scenarioId)
  const nav: { id: View; label: string; icon: ReactNode }[] = [
    { id: 'welcome', label: 'Welcome', icon: <Home size={15} /> },
    { id: 'twin', label: 'Living Twin', icon: <Globe size={15} /> },
    { id: 'experiment', label: 'Experiment', icon: <FlaskConical size={15} /> },
    { id: 'agents', label: 'Agents', icon: <Bot size={15} /> },
    { id: 'attackpath', label: 'Attack Path', icon: <Route size={15} /> },
    { id: 'verification', label: 'Verification Lab', icon: <ShieldCheck size={15} /> },
    { id: 'evidence', label: 'Evidence', icon: <FileText size={15} /> },
    { id: 'designer', label: 'Twin Designer', icon: <PenTool size={15} /> },
    { id: 'playbook', label: 'Playbook', icon: <Swords size={15} /> },
    { id: 'library', label: 'Library', icon: <Boxes size={15} /> },
    { id: 'settings', label: 'Settings', icon: <SettingsIcon size={15} /> },
  ]
  const live = s.modelStatus?.mode === 'live'

  return (
    <div className="min-h-screen bg-[#020617] text-slate-100">
      <header className="flex flex-wrap items-center gap-3 border-b border-cyan-900/60 px-4 py-2 bg-slate-950/80 backdrop-blur">
        <div className="font-black tracking-[0.3em] text-cyan-300">CYBERGENESIS</div>
        <span className={`text-[11px] font-mono px-2 py-1 rounded-full border ${live ? 'border-emerald-400 text-emerald-300' : 'border-amber-400 text-amber-300'}`}>
          {live ? '● LIVE META AI' : '● OFFLINE SIMULATION'} — {s.modelStatus?.model ?? 'muse-spark-1.3'}
        </span>
        <span className="text-[11px] text-slate-400 font-mono">{s.modelStatus?.detail}</span>
        {s.results?.usage && s.results.usage.calls > 0 && (
          <span className="text-[11px] font-mono px-2 py-1 rounded-full border border-violet-500/60 text-violet-300" title="Real Meta Model API usage for the current run">
            Meta tokens: {s.results.usage.prompt_tokens} in + {s.results.usage.completion_tokens} out · {s.results.usage.calls} calls
          </span>
        )}
        <nav className="ml-auto flex flex-wrap gap-1" aria-label="Primary">
          {nav.map((n) => (
            <button key={n.id} onClick={() => s.set({ view: n.id })}
              className={`flex items-center gap-1 px-2 py-1.5 rounded text-xs ${s.view === n.id ? 'bg-cyan-500/20 text-cyan-200 border border-cyan-500/50' : 'text-slate-300 hover:bg-slate-800'}`}>
              {n.icon}{n.label}</button>
          ))}
        </nav>
      </header>

      {s.error && <div role="alert" className="mx-4 mt-3 rounded border border-red-500/60 bg-red-950/50 px-3 py-2 text-sm text-red-200">{s.error}</div>}

      {s.view === 'welcome' && (
        <main className="relative overflow-hidden px-6 py-16 text-center">
          <motion.h1 initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} className="text-6xl md:text-8xl font-black tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-sky-400 to-emerald-300">CYBERGENESIS</motion.h1>
          <p className="mt-4 text-xl text-slate-300">The Autonomous Self-Defending Digital Twin</p>
          <p className="mx-auto mt-3 max-w-2xl text-sm text-slate-400">Observe → Reason → Propose → Validate → Act → Retest → Prove. A closed-loop autonomous defense experiment on a synthetic enterprise twin — every result computed, replayed, and evidenced. Synthetic data only; no real targets.</p>
          <div className={`mx-auto mt-6 w-fit rounded-full border px-4 py-2 font-mono text-sm ${live ? 'border-emerald-400 text-emerald-300' : 'border-amber-400 text-amber-300'}`}>
            <span className="animate-pulse">●</span> {live ? 'LIVE META AI — Muse Spark is reasoning on this twin' : 'OFFLINE SIMULATION — deterministic mode (set MODEL_API_KEY for LIVE META AI)'}
          </div>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <button onClick={() => s.set({ view: 'twin' })} className="rounded-lg bg-cyan-500 px-5 py-3 font-semibold text-slate-950 hover:bg-cyan-400">Enter the Digital Twin</button>
            <button onClick={() => void runDemo('ransomware_activity')} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-5 py-3 font-semibold text-slate-950 hover:bg-emerald-400"><Play size={16} /> Run Autonomous Defense Demo</button>
            <button onClick={() => s.set({ view: 'agents' })} className="rounded-lg border border-cyan-700 px-5 py-3 hover:bg-slate-800">Explore Architecture</button>
            <button onClick={exportReport} disabled={!s.runId} className="rounded-lg border border-slate-600 px-5 py-3 disabled:opacity-40" title={s.runId ? 'Download evidence report' : 'Run an experiment first'}><Download size={15} className="inline" /> Download Report</button>
          </div>
          <p className="mt-10 text-xs font-mono text-slate-500">Powered by Meta Muse Spark · Created by Dr. Abhirup Guha · Meta Global AI Developer Hackathon 2026</p>
          <div className="mx-auto mt-8 h-[380px] max-w-5xl rounded-2xl border border-cyan-900 overflow-hidden">
            {s.twin ? <TwinView twin={s.twin} /> : <div className="p-8 text-slate-400">Loading twin… (backend on :8000 required)</div>}
          </div>
        </main>
      )}

      {s.view === 'twin' && (
        <main className="grid grid-cols-12 gap-3 p-3">
          <aside className="col-span-12 lg:col-span-2 space-y-3">
            <section className="rounded-xl border border-slate-800 glass-panel p-3">
              <h2 className="mb-2 flex items-center gap-1 text-xs font-bold tracking-wider text-cyan-300"><Network size={13} /> ASSETS</h2>
              {s.twin?.assets.map((a) => (
                <button key={a.id} onClick={() => s.set({ selectedAsset: a.id })} className="block w-full text-left text-xs py-1 hover:text-cyan-200">
                  <span style={{ color: STATUS_COLOR[a.status] }}>●</span> <span style={{ color: STATUS_COLOR[a.status] }}>{ASSET_TYPE_ICON[a.asset_type]}</span> {a.name} <span className="text-slate-500">({a.status})</span>
                </button>
              ))}
            </section>
            <section className="rounded-xl border border-slate-800 glass-panel p-3">
              <h2 className="mb-1 text-xs font-bold tracking-wider text-cyan-300">TOPOLOGY</h2>
              <div className="text-xs text-slate-300">{s.twin?.assets.length ?? 0} assets · {s.twin?.connections.length ?? 0} connections</div>
              <div className="text-xs text-slate-400 mt-1">{s.twin?.connections.filter((c) => c.active).length ?? 0} active · {s.twin?.connections.filter((c) => !c.active).length ?? 0} blocked/isolated</div>
              <div className="text-xs text-slate-400">Containment: {s.twin?.containment.length ? s.twin.containment.join(', ') : 'none'}</div>
              <div className="mt-2 space-y-0.5">
                {s.twin?.assets.map((a) => (
                  <div key={a.id} className="flex justify-between text-[11px]"><span className="text-slate-400">{a.name}</span><span style={{ color: STATUS_COLOR[a.status] }}>{a.status}</span></div>
                ))}
              </div>
            </section>
            <section className="rounded-xl border border-emerald-900/60 bg-emerald-950/30 p-3">
              <h2 className="mb-1 text-xs font-bold tracking-wider text-emerald-300">RUN AN EXPERIMENT</h2>
              <p className="text-[11px] text-slate-400">The Living Twin is for inspection. Attacks, agent reasoning and verification live in the Experiment console.</p>
              <button onClick={() => s.set({ view: 'experiment' })} className="mt-2 flex w-full items-center justify-center gap-1 rounded bg-emerald-500 py-2 text-xs font-bold text-slate-950"><Play size={13} /> Open Experiment Console</button>
              <button onClick={() => void resetAll()} className="mt-1 flex w-full items-center justify-center gap-1 rounded border border-slate-600 py-2 text-xs"><RotateCcw size={13} /> Reset Twin State</button>
            </section>
          </aside>

          <section className="col-span-12 lg:col-span-7">
            <div className="h-[520px] rounded-2xl border border-cyan-900 overflow-hidden bg-slate-950">
              {s.twin
                ? s.viewMode === '3d' ? <TwinView twin={s.twin} /> : <Twin2D twin={s.twin} />
                : <div className="p-6 text-slate-400">Loading twin…</div>}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <button onClick={() => s.set({ viewMode: s.viewMode === '3d' ? '2d' : '3d' })} className="rounded border border-slate-600 px-2 py-1">Toggle {s.viewMode === '3d' ? '2D (accessible)' : '3D'}</button>
              <MapFocusToggle />
              <span className="text-slate-500 py-1">Drag to orbit · scroll to zoom · click node to inspect · status also available as text in the asset list</span>
            </div>
            <AttackChain />
            <section className="mt-3 max-h-56 overflow-auto rounded-xl border border-slate-800 glass-panel p-3" aria-label="Event timeline">
              <h2 className="mb-2 flex items-center gap-1 text-xs font-bold tracking-wider text-cyan-300"><Activity size={13} /> EVENT TIMELINE</h2>
              {s.events.length === 0 && <p className="text-xs text-slate-500">No events yet. Run a simulation.</p>}
              {[...s.events].reverse().map((e, i) => (
                <div key={i} className="border-b border-slate-800 py-1 text-xs">
                  <span className="font-mono text-cyan-400">{e.event_type}</span>
                  {e.agent && <span className="text-violet-300"> · {e.agent}</span>}
                  {e.asset_id && <span className="text-amber-300"> · {e.asset_id}</span>}
                  <span className="text-slate-300"> — {e.message}</span>
                </div>
              ))}
            </section>
          </section>

          <aside className="col-span-12 lg:col-span-3 rounded-xl border border-slate-800 glass-panel p-3">
            <h2 className="mb-2 text-xs font-bold tracking-wider text-cyan-300">CONTEXT</h2>
            {selected ? <AssetPanel asset={selected} /> : <p className="text-sm text-slate-400">Select a node in 3D, or an asset in the left list, to inspect posture, connections and evidence context.</p>}
            {scenario && <div className="mt-4 border-t border-slate-800 pt-3 text-sm"><b>{scenario.name}</b><p className="text-slate-400 text-xs mt-1">{scenario.description}</p><p className="text-xs mt-2 text-emerald-300">Invariant: {scenario.invariant}</p></div>}
            {s.results?.verification && (
              <div className="mt-4 border-t border-slate-800 pt-3 text-sm">
                <div className={`font-black ${s.results.verification.outcome === 'PASS' ? 'text-emerald-300' : 'text-red-300'}`}>VERIFICATION: {s.results.verification.outcome}</div>
                <button onClick={() => s.set({ view: 'verification' })} className="mt-1 text-xs text-cyan-300 underline">Open Verification Lab</button>
              </div>
            )}
          </aside>
        </main>
      )}

      {s.view === 'experiment' && (
        <main className="p-3">
          <div className="flex flex-wrap items-end justify-between gap-2 px-1">
            <div>
              <h1 className="text-2xl font-black text-cyan-200">Autonomous Experiment Console</h1>
              <p className="text-xs text-slate-400">Select a scenario → run the closed loop → watch agents reason, policy gate, defend, and verify. Seed 42 (deterministic).</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-lg border border-slate-700 overflow-hidden text-xs" role="group" aria-label="Demo speed">
                {[1, 2, 4].map((v) => <button key={v} onClick={() => setSpeed(v)} className={`px-2 py-2 ${speed === v ? 'bg-cyan-600 text-white' : 'text-slate-300'}`}>{v}×</button>)}
              </div>
              <button onClick={() => setCinematic(true)} className="rounded-lg border border-violet-600 px-3 py-2 text-sm text-violet-200">⛶ Cinematic</button>
              <button onClick={() => void runDemo()} className="flex items-center gap-1 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-bold text-slate-950"><Play size={14} /> RUN EXPERIMENT</button>
              <button onClick={() => void resetAll()} className="flex items-center gap-1 rounded-lg border border-slate-600 px-3 py-2 text-sm"><RotateCcw size={14} /> Reset</button>
              <button onClick={exportReport} disabled={!s.runId} className="rounded-lg border border-slate-600 px-3 py-2 text-sm disabled:opacity-40"><Download size={14} className="inline" /> JSON</button>
              <button onClick={() => downloadMarkdown()} disabled={!s.runId} className="rounded-lg border border-slate-600 px-3 py-2 text-sm disabled:opacity-40"><Download size={14} className="inline" /> Report .md</button>
            </div>
          </div>

          {/* stage stepper */}
          <ol className="mt-3 flex flex-wrap gap-1" aria-label="Experiment stages">
            {STAGES.map((st, i) => {
              const cur = STAGES.indexOf(s.runState)
              const done = i < cur || s.runState === 'COMPLETED'
              const active = i === cur && s.runState !== 'COMPLETED'
              return <li key={st} className={`rounded-full border px-2 py-1 font-mono text-[10px] ${done ? 'border-emerald-500 text-emerald-300' : active ? 'border-cyan-300 bg-cyan-500/20 text-cyan-200 animate-pulse' : 'border-slate-700 text-slate-500'}`}>{done ? '✓' : i + 1} {st.replaceAll('_', ' ')}</li>
            })}
          </ol>

          {/* scenario picker */}
          <section className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4" aria-label="Select scenario">
            {s.scenarios.map((sc) => (
              <button key={sc.id} onClick={() => s.set({ scenarioId: sc.id })} className={`rounded-xl border p-3 text-left ${s.scenarioId === sc.id ? 'border-cyan-300 bg-cyan-500/15' : 'border-slate-800 glass-panel hover:border-slate-600'}`}>
                <div className="text-sm font-bold">{SCENARIO_ICONS[sc.id]} {sc.name} <span className="text-amber-300 text-xs">({sc.severity})</span></div>
                <p className="mt-1 line-clamp-2 text-[11px] text-slate-400">{sc.description}</p>
                <p className="mt-1 font-mono text-[10px] text-slate-500">{sc.source_asset} → {sc.target_asset}</p>
              </button>
            ))}
          </section>

          <div className="mt-3 grid grid-cols-12 gap-3">
            <section className="col-span-12 lg:col-span-8">
              <div className="h-[430px] rounded-2xl border border-cyan-900 overflow-hidden bg-slate-950">
                {s.twin ? (s.viewMode === '3d' ? <TwinView twin={s.twin} /> : <Twin2D twin={s.twin} />) : <SkeletonTwin />}
              </div>
              <div className="mt-2 flex items-center gap-2"><MapFocusToggle /><span className="text-[11px] text-slate-500">Focus mode dims everything except the attack path — switch to Full topology to inspect all connections.</span></div>
              <AttackChain />
              <section className="mt-3 max-h-64 overflow-auto rounded-xl border border-slate-800 glass-panel p-3" aria-label="Live event timeline">
                <h2 className="mb-2 flex items-center gap-1 text-xs font-bold tracking-wider text-cyan-300"><Activity size={13} /> LIVE EVENT TIMELINE <span className="font-mono text-slate-500">· state: {s.runState}</span></h2>
                {s.events.length > 0 && (
                  <div className="mb-2 flex items-center gap-2 rounded bg-slate-950/70 px-2 py-1.5">
                    <button onClick={() => { setReplayIdx(replayIdx === null ? -1 : replayIdx); setReplayPlaying(!replayPlaying) }} className="rounded bg-cyan-600 px-2 py-0.5 text-[11px] font-bold">{replayPlaying ? '❚❚ Pause replay' : '▶ Replay attack'}</button>
                    <input type="range" min={0} max={Math.max(s.events.length - 1, 0)} value={replayIdx ?? s.events.length - 1}
                      onChange={(e) => { const i = Number(e.target.value); setReplayIdx(i); const ev = s.events[i]; if (ev?.asset_id) s.set({ selectedAsset: ev.asset_id }) }}
                      className="flex-1" aria-label="Timeline scrubber" />
                    <span className="font-mono text-[10px] text-slate-400">{(replayIdx ?? s.events.length - 1) + 1}/{s.events.length}</span>
                    {snapshots.map((sn) => <span key={sn.label} className="rounded-full border border-slate-700 px-1.5 py-0.5 font-mono text-[9px] text-slate-400">{sn.label}: {Object.values(sn.snapshot.status).filter((v) => v === 'compromised').length}✗ {Object.values(sn.snapshot.status).filter((v) => v === 'healthy' || v === 'remediated').length}✓</span>)}
                  </div>
                )}
                {replayIdx !== null && s.events[replayIdx] && (
                  <p className="mb-2 rounded border border-amber-700/60 bg-amber-950/30 px-2 py-1 text-[11px] text-amber-200">Replay @{replayIdx + 1}: [{s.events[replayIdx].event_type}] {s.events[replayIdx].message}</p>
                )}
                {s.events.length === 0 && <p className="text-xs text-slate-500">No events yet — press RUN EXPERIMENT. (Space also runs, R resets, 1–4 pick a scenario.)</p>}
                {[...s.events].reverse().map((e, i) => (
                  <div key={i} className={`border-b border-slate-800 py-1 text-xs ${replayIdx === s.events.length - 1 - i ? 'bg-amber-500/15' : ''}`}>
                    <span className="font-mono text-cyan-400">{e.event_type}</span>
                    {e.agent && <span className="text-violet-300"> · {e.agent}</span>}
                    {e.asset_id && <span className="text-amber-300"> · {e.asset_id}</span>}
                    <span className="text-slate-300"> — {e.message}</span>
                  </div>
                ))}
              </section>
            </section>
            <aside className="col-span-12 lg:col-span-4 space-y-3">
              <section className="rounded-xl border border-violet-800/60 bg-violet-950/30 p-3" aria-live="polite">
                <h2 className="mb-1 flex items-center justify-between text-xs font-bold tracking-wider text-violet-300">
                  <span className="flex items-center gap-1"><MessageSquareText size={13} /> DEMO COMMENTARY</span>
                  <button onClick={() => setCommentaryOn(!commentaryOn)} className="text-[10px] text-slate-400 underline">{commentaryOn ? 'hide' : 'show'}</button>
                </h2>
                {commentaryOn && <><p className="font-mono text-[10px] text-violet-400">DEMO {DEMO_CLOCK[s.runState] ?? ''} · stage {s.runState}</p><p className="mt-0.5 text-sm leading-relaxed text-slate-100">{commentary}</p></>}
              </section>
              <section className="rounded-xl border border-slate-800 glass-panel p-3">
                <h2 className="mb-2 text-xs font-bold tracking-wider text-cyan-300">AGENT DECISIONS THIS RUN</h2>
                {(s.results?.decisions.length ?? 0) === 0 && <p className="text-xs text-slate-500">Decisions appear here as agents act (also live in the timeline).</p>}
                {s.results?.decisions.map((d, i) => (
                  <div key={i} className="mb-1 rounded bg-slate-950/60 px-2 py-1.5 text-xs">
                    <span className="text-violet-300">{d.agent}</span> <span className="text-slate-500">({d.model}/{d.mode}, {(d.confidence * 100).toFixed(0)}%)</span>
                    <div className="text-slate-200">{d.decision}</div>
                  </div>
                ))}
                {s.results?.policy.map((p, i) => (
                  <div key={i} className={`text-xs ${p.approved ? 'text-emerald-300' : 'text-red-300'}`}>{p.approved ? '✓ POLICY APPROVED' : '✗ POLICY REJECTED'}: {p.action_type} on {p.asset_id}</div>
                ))}
              </section>
              <CandidatesPanel />
              <section className="rounded-xl border border-slate-800 glass-panel p-3">
                <h2 className="mb-1 text-xs font-bold tracking-wider text-cyan-300">OUTCOME</h2>
                {s.results?.verification ? (
                  <>
                    <div className={`text-2xl font-black ${s.results.verification.outcome === 'PASS' ? 'text-emerald-300' : 'text-red-300'}`}>{s.results.verification.outcome}</div>
                    <p className="text-xs text-slate-400">Effectiveness {String(s.results.verification.metrics.defense_effectiveness_pct)}% · disrupted legit paths: {String(s.results.verification.metrics.operational_impact_disrupted_legit_paths)}</p>
                    <button onClick={() => s.set({ view: 'verification' })} className="mt-1 text-xs text-cyan-300 underline">Open Verification Lab →</button>
                  </>
                ) : <p className="text-xs text-slate-500">No outcome yet. A failed or rejected defense will show FAIL here — honestly.</p>}
              </section>
            </aside>
          </div>
        </main>
      )}

      {s.view === 'agents' && (
        <main className="p-6">
          <h1 className="text-2xl font-black text-cyan-200">Agent Collaboration</h1>
          <p className="text-sm text-slate-400 mt-1">Six specialised agents, one orchestrated state machine. Only the Investigator and Strategist use Meta Muse Spark; provider failure is shown honestly, never faked.</p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {AGENTS.map((a, i) => {
              const active = s.events.some((e) => e.agent === a.id)
              const decisions = s.results?.decisions.filter((d) => d.agent === a.id) ?? []
              const isSel = selectedAgent === a.id
              return (
                <motion.section key={a.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                  onClick={() => setSelectedAgent(a.id)} role="button" tabIndex={0} aria-pressed={isSel}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedAgent(a.id) } }}
                  className={`cursor-pointer rounded-xl border p-4 transition hover:border-cyan-500 ${isSel ? 'border-cyan-300 bg-cyan-500/15 ring-1 ring-cyan-400' : active ? 'border-cyan-400 bg-cyan-950/40' : 'border-slate-800 glass-panel'}`}>
                  <div className="flex items-center gap-2"><Bot className="text-cyan-300" size={18} /><b>{a.name}</b>{active && <span className="text-[10px] text-emerald-300 font-mono">ACTIVE</span>}<span className="ml-auto text-[10px] text-slate-500">{isSel ? 'inspecting ▾' : 'click to inspect'}</span></div>
                  <p className="mt-1 text-xs text-slate-400">{a.desc}</p>
                  <p className="font-mono text-[10px] text-slate-500">{a.engine}</p>
                  {decisions.map((d, j) => (
                    <div key={j} className="mt-2 rounded bg-slate-950/70 p-2 text-xs">
                      <div>{d.decision}</div>
                      <div className="text-slate-400 mt-1">{d.justification}</div>
                      <div className="font-mono text-[10px] mt-1 text-slate-500">confidence {(d.confidence * 100).toFixed(0)}% · {d.model} · mode={d.mode}</div>
                      <details className="mt-1"><summary className="cursor-pointer text-cyan-300">Raw decision JSON</summary>
                        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[10px] text-slate-400">{JSON.stringify(d, null, 2)}</pre></details>
                    </div>
                  ))}
                </motion.section>
              )
            })}
          </div>
          {(() => {
            const a = AGENTS.find((x) => x.id === selectedAgent) ?? AGENTS[0]
            const agentEvents = s.events.filter((e) => e.agent === a.id)
            const agentDecisions = s.results?.decisions.filter((d) => d.agent === a.id) ?? []
            return (
              <section className="mt-4 rounded-2xl border border-cyan-800 glass-panel p-5" aria-label="Agent inspector">
                <div className="flex flex-wrap items-center gap-2">
                  <Bot className="text-cyan-300" /><h2 className="text-lg font-black">{a.name}</h2>
                  <span className="rounded-full border border-slate-600 px-2 py-0.5 font-mono text-[10px] text-slate-300">{a.engine}</span>
                  <span className={`rounded-full border px-2 py-0.5 font-mono text-[10px] ${agentEvents.length ? 'border-emerald-500 text-emerald-300' : 'border-slate-700 text-slate-500'}`}>{agentEvents.length ? `${agentEvents.length} events this run` : 'no activity yet — run an experiment'}</span>
                </div>
                <div className="mt-3 grid gap-4 md:grid-cols-3 text-sm">
                  <div><h3 className="text-xs font-bold tracking-wider text-cyan-300">RESPONSIBILITIES</h3>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-slate-300">{a.duties.map((d) => <li key={d}>{d}</li>)}</ul></div>
                  <div><h3 className="text-xs font-bold tracking-wider text-cyan-300">CONTRACT</h3>
                    <p className="mt-1 text-xs text-slate-300">Input: <span className="font-mono">{a.input}</span></p>
                    <p className="text-xs text-slate-300">Output: <span className="font-mono text-emerald-300">{a.output}</span></p>
                    <p className="mt-1 text-[11px] text-slate-500">Output is schema-validated; the Executor/Verifier are deterministic and independent of the LLM.</p></div>
                  <div><h3 className="text-xs font-bold tracking-wider text-cyan-300">LATEST ACTIVITY</h3>
                    {agentEvents.length === 0 && agentDecisions.length === 0 && <p className="mt-1 text-xs text-slate-500">Nothing yet for this run.</p>}
                    {agentDecisions.map((d, i) => <p key={i} className="mt-1 text-xs text-slate-200">{d.decision} <span className="text-slate-500">({(d.confidence * 100).toFixed(0)}% · {d.mode})</span></p>)}
                    {agentEvents.slice(-4).map((e, i) => <p key={i} className="mt-1 font-mono text-[10px] text-slate-400">{e.event_type}: {e.message.slice(0, 110)}</p>)}
                  </div>
                </div>
              </section>
            )
          })()}
        </main>
      )}

      {s.view === 'attackpath' && (
        <main className="p-6 max-w-4xl">
          <h1 className="text-2xl font-black text-cyan-200">Attack Path Explorer</h1>
          {scenario ? (
            <div className="mt-4 space-y-3 text-sm">
              <p className="text-slate-300">{scenario.name}: entry <b className="text-amber-300">{scenario.source_asset}</b> → protected target <b className="text-red-300">{scenario.target_asset}</b></p>
              <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
                {(s.results?.verification?.metrics.after_path as string[] | null | undefined) !== undefined && s.results?.verification
                  ? <span>Path after defense: {(s.results.verification.metrics.after_path as string[] | null)?.join(' → ') ?? 'UNREACHABLE (blocked)'}</span>
                  : <span className="text-slate-400">Run the experiment to compute the live graph path (NetworkX/BFS on the twin).</span>}
              </div>
              <p>Baseline path: {((s.results?.verification?.metrics.baseline_path as string[] | null)?.join(' → ')) ?? 'run experiment first'}</p>
              <p className="text-emerald-300">Invariant: {scenario.invariant}</p>
              <p className="text-slate-400 text-xs">Segmentation is applied only through the policy-gated allowlist (block_connection / isolate_asset / session revocation). Verification replays the identical objective.</p>
              <div className="h-[360px] rounded-xl border border-cyan-900 overflow-hidden">{s.twin && <TwinView twin={s.twin} />}</div>
            </div>
          ) : <p className="text-slate-400">Select a scenario first.</p>}
        </main>
      )}

      {s.view === 'verification' && (
        <main className="p-6 max-w-5xl">
          <h1 className="text-2xl font-black text-cyan-200">Defense Verification Lab</h1>
          {!s.results?.verification ? <p className="mt-3 text-slate-400">No verification yet. Run an experiment — failed experiments are shown honestly here too.</p> : (
            <div>
              <div className={`mt-3 text-3xl font-black ${s.results.verification.outcome === 'PASS' ? 'text-emerald-300' : 'text-red-300'}`}>{s.results.verification.outcome}</div>
              <p className="text-sm text-slate-300">{s.results.verification.invariant}</p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <section className="rounded-xl border border-red-900/60 glass-panel p-4"><h2 className="font-bold text-red-300">BEFORE DEFENSE</h2>
                  <p className="text-sm mt-2">Attack objective reachable/granted: {String(s.results.verification.metrics.baseline_reachable_or_granted)}</p>
                  <p className="text-xs text-slate-400">Path: {(s.results.verification.metrics.baseline_path as string[] | null)?.join(' → ') ?? 'identity session'}</p></section>
                <section className="rounded-xl border border-emerald-900/60 glass-panel p-4"><h2 className="font-bold text-emerald-300">AFTER DEFENSE</h2>
                  <p className="text-sm mt-2">Attack objective reachable/granted: {String(s.results.verification.metrics.after_reachable_or_granted)}</p>
                  <p className="text-xs text-slate-400">Path: {(s.results.verification.metrics.after_path as string[] | null)?.join(' → ') ?? 'none / denied'}</p></section>
              </div>
              <dl className="mt-4 grid gap-2 md:grid-cols-4 text-center">
                {[['Defense effectiveness', `${s.results.verification.metrics.defense_effectiveness_pct}%`],
                  ['Time to detect', `${s.results.verification.metrics.time_to_detect_s}s`],
                  ['Time to contain', `${s.results.verification.metrics.time_to_contain_s ?? '—'}s`],
                  ['Legit paths disrupted', `${s.results.verification.metrics.operational_impact_disrupted_legit_paths}`]].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-slate-800 glass-panel p-3"><dt className="text-[11px] text-slate-400">{k}</dt><dd className="text-xl font-black text-cyan-200">{v}</dd></div>
                ))}
              </dl>
              <ul className="mt-4 space-y-1 text-sm">{s.results.verification.checks.map((c) => (
                <li key={c.name} className={c.passed ? 'text-emerald-300' : 'text-red-300'}>{c.passed ? '✓' : '✗'} {c.name} — <span className="text-slate-300">{c.detail}</span></li>))}
              </ul>
              <ResilienceCurve />
              <div className="mt-4"><CandidatesPanel /></div>
              <p className="mt-4 text-slate-300 font-semibold">CYBERGENESIS does not merely detect cyberattacks. It tests defenses and verifies resilience.</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button onClick={() => void runDemo(s.scenarioId, true)} className="flex items-center gap-1 rounded bg-cyan-600 px-3 py-2 text-xs font-bold"><RotateCcw size={13} /> Replay with Seed 42</button>
                <button onClick={() => void downloadMarkdown()} className="flex items-center gap-1 rounded border border-slate-600 px-3 py-2 text-xs"><Download size={13} /> Download Report (.md)</button>
                <span className="text-xs text-slate-400">Deterministic replay: identical seed produces identical telemetry (proven in backend tests).</span>
              </div>
              {s.replayVerdict && <p className="mt-2 rounded border border-emerald-700 bg-emerald-950/40 px-3 py-2 text-xs text-emerald-200">{s.replayVerdict}</p>}
            </div>
          )}
        </main>
      )}

      {s.view === 'designer' && <Suspense fallback={<div className="p-6 text-slate-400">Loading Twin Designer…</div>}><TwinDesigner /></Suspense>}
      {s.view === 'playbook' && <Suspense fallback={<div className="p-6 text-slate-400">Loading Attack Playbook…</div>}><AttackPlaybook onRunCustom={(sid, tid) => void runCustomExperiment(sid, tid)} /></Suspense>}
      {s.view === 'library' && <Suspense fallback={<div className="p-6 text-slate-400">Loading Component Library…</div>}><ComponentLibrary /></Suspense>}
      {s.view === 'evidence' && <EvidenceView />}
      {s.view === 'settings' && (
        <main className="p-6 max-w-2xl space-y-3 text-sm">
          <h1 className="text-2xl font-black text-cyan-200">System Settings</h1>
          <div className="rounded-xl border border-slate-800 glass-panel p-4 space-y-1">
            <div className="flex items-center gap-2"><Database size={15} /> Model: {s.modelStatus?.model} · Provider: Meta Model API</div>
            <div>Mode: <b>{s.modelStatus?.mode}</b> · Configured: {String(s.modelStatus?.configured)} · Reachable: {String(s.modelStatus?.reachable)}</div>
            <div className="text-slate-400">{s.modelStatus?.detail}</div>
            <div className="text-slate-500 text-xs">API keys are read from backend environment only and are never displayed. Set MODEL_API_KEY + restart backend for LIVE META AI; otherwise the app runs in clearly-labelled OFFLINE SIMULATION mode.</div>
          </div>
          <button onClick={() => void resetAll()} className="rounded bg-red-500/80 px-4 py-2 font-semibold text-white">Reset twin &amp; clear current run view</button>
          <button onClick={exportReport} disabled={!s.runId} className="ml-2 rounded border border-slate-600 px-4 py-2 disabled:opacity-40"><Download size={14} className="inline" /> Export report JSON</button>
        </main>
      )}

      {cinematic && (
        <div className="fixed inset-0 z-50 bg-[#020617]/97 p-4" role="dialog" aria-label="Cinematic twin mode">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-xs tracking-widest text-cyan-300">CINEMATIC — {scenario?.name ?? 'DIGITAL TWIN'} · stage {s.runState}</span>
            <button onClick={() => setCinematic(false)} className="rounded-full border border-slate-600 px-3 py-1 text-xs">✕ Exit (Esc)</button>
          </div>
          <div className="h-[78vh] rounded-2xl border border-cyan-900 overflow-hidden">
            {s.twin ? <TwinView twin={s.twin} /> : <SkeletonTwin />}
          </div>
          <AttackChain />
          <p className="mt-2 text-center text-sm text-violet-200" aria-live="polite">{commentary}</p>
        </div>
      )}

      <footer className="border-t border-slate-800 px-4 py-3 text-center text-[11px] text-slate-500">
        CYBERGENESIS · synthetic simulation only · no real targets, scanning, or exploitation · Created by Dr. Abhirup Guha
      </footer>
    </div>
  )
}

function EvidenceView() {
  const s = useStore()
  const load = () => { if (s.runId) api.evidence(s.runId).then((ev) => useStore.setState({ events: ev.map((e) => ({ event_type: e.kind, message: `${e.ref} — ${e.summary}` })) })).catch(() => undefined) }
  return (
    <main className="p-6 max-w-4xl">
      <h1 className="text-2xl font-black text-cyan-200">Experiment Evidence</h1>
      <p className="text-sm text-slate-400">Append-only audit trail stored in the backend database. Every record below came from a stored run.</p>
      <div className="mt-3 flex gap-2">
        <button onClick={load} className="rounded bg-cyan-600 px-3 py-1.5 text-xs font-bold">Load evidence for current run</button>
        <button onClick={() => s.runId && api.report(s.runId).then((r) => {
          const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' })
          const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `cybergenesis-report-${s.runId}.json`; a.click()
        })} disabled={!s.runId} className="rounded border border-slate-600 px-3 py-1.5 text-xs disabled:opacity-40">Export report</button>
      </div>
      <div className="mt-4 space-y-1">{s.events.map((e, i) => (
        <div key={i} className="rounded border border-slate-800 glass-panel px-3 py-2 text-xs"><span className="font-mono text-cyan-300">{e.event_type}</span> <span className="text-slate-300">{e.message}</span></div>
      ))}</div>
    </main>
  )
}
