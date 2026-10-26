import { Component, useEffect, useRef, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  Activity, Bot, Database, Download, FlaskConical, Globe, Play, RotateCcw, Route,
  Settings as SettingsIcon, Shield, ShieldCheck, Siren, Home, Network, FileText,
} from 'lucide-react'
import TwinScene, { STATUS_COLOR } from './components/TwinScene'
import { api, WS } from './services/api'
import { useStore } from './stores/store'
import type { Asset, Twin, View } from './types'

const AGENTS = [
  { id: 'observer', name: 'Observer', desc: 'Deterministic telemetry anomaly detection' },
  { id: 'adversary_simulator', name: 'Adversary Simulator', desc: 'Typed, bounded synthetic scenario actions' },
  { id: 'incident_investigator', name: 'Incident Investigator', desc: 'Meta Muse Spark evidence-grounded reasoning' },
  { id: 'defense_strategist', name: 'Defense Strategist', desc: 'Meta Muse Spark countermeasure proposals' },
  { id: 'defense_executor', name: 'Defense Executor', desc: 'Deterministic policy gate + allowlisted execution' },
  { id: 'verification_scientist', name: 'Verification Scientist', desc: 'Independent replay & invariant checking' },
]
const STAGES = ['SCENARIO_SELECTED', 'ATTACK_SIMULATING', 'TELEMETRY_COLLECTED', 'INVESTIGATING', 'DEFENSE_PROPOSED', 'POLICY_VALIDATING', 'DEFENSE_APPLYING', 'VERIFYING', 'COMPLETED']

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
      if (r.run.state === 'COMPLETED' || r.run.state === 'FAILED') stopPoll()
    } catch { /* polling is best-effort; WS is primary */ }
  }

  async function runDemo(scenarioId = s.scenarioId) {
    s.set({ error: null, events: [], results: null, runState: 'SCENARIO_SELECTED', view: 'experiment', scenarioId })
    try {
      await api.reset()
      const created = await api.createExperiment(scenarioId, 42)
      s.set({ runId: created.id })
      await api.runExperiment(created.id)
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

  async function resetAll() {
    stopPoll(); wsRef.current?.close()
    try { const r = await api.reset(); s.set({ twin: r.twin, events: [], results: null, runState: 'IDLE', error: null }) }
    catch (e) { s.set({ error: (e as Error).message }) }
  }

  function exportReport() {
    if (!s.runId) return
    api.report(s.runId).then((r) => {
      const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' })
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
      a.download = `cybergenesis-report-${s.runId}.json`; a.click()
    }).catch((e) => s.set({ error: (e as Error).message }))
  }

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
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <button onClick={() => s.set({ view: 'twin' })} className="rounded-lg bg-cyan-500 px-5 py-3 font-semibold text-slate-950 hover:bg-cyan-400">Enter the Digital Twin</button>
            <button onClick={() => void runDemo('ransomware_activity')} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-5 py-3 font-semibold text-slate-950 hover:bg-emerald-400"><Play size={16} /> Run Autonomous Defense Demo</button>
            <button onClick={() => s.set({ view: 'agents' })} className="rounded-lg border border-cyan-700 px-5 py-3 hover:bg-slate-800">Explore Architecture</button>
          </div>
          <p className="mt-10 text-xs font-mono text-slate-500">Powered by Meta Muse Spark · Created by Dr. Abhirup Guha · Meta Global AI Developer Hackathon 2026</p>
          <div className="mx-auto mt-8 h-[380px] max-w-5xl rounded-2xl border border-cyan-900 overflow-hidden">
            {s.twin ? <SceneBoundary fallback={<Twin2D twin={s.twin} />}><TwinScene twin={s.twin} /></SceneBoundary> : <div className="p-8 text-slate-400">Loading twin… (backend on :8000 required)</div>}
          </div>
        </main>
      )}

      {(s.view === 'twin' || s.view === 'experiment') && (
        <main className="grid grid-cols-12 gap-3 p-3">
          <aside className="col-span-12 lg:col-span-2 space-y-3">
            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h2 className="mb-2 flex items-center gap-1 text-xs font-bold tracking-wider text-cyan-300"><Network size={13} /> ASSETS</h2>
              {s.twin?.assets.map((a) => (
                <button key={a.id} onClick={() => s.set({ selectedAsset: a.id })} className="block w-full text-left text-xs py-1 hover:text-cyan-200">
                  <span style={{ color: STATUS_COLOR[a.status] }}>●</span> {a.name} <span className="text-slate-500">({a.status})</span>
                </button>
              ))}
            </section>
            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h2 className="mb-2 flex items-center gap-1 text-xs font-bold tracking-wider text-cyan-300"><Siren size={13} /> SCENARIOS</h2>
              {s.scenarios.map((sc) => (
                <button key={sc.id} onClick={() => s.set({ scenarioId: sc.id })} className={`block w-full rounded p-2 text-left text-xs mb-1 ${s.scenarioId === sc.id ? 'bg-cyan-500/20 border border-cyan-600' : 'bg-slate-800/60'}`}>{sc.name} <span className="text-amber-300">({sc.severity})</span></button>
              ))}
              <button onClick={() => void runDemo()} className="mt-2 flex w-full items-center justify-center gap-1 rounded bg-emerald-500 py-2 text-xs font-bold text-slate-950"><Play size={13} /> RUN SIMULATION</button>
              <button onClick={() => void resetAll()} className="mt-1 flex w-full items-center justify-center gap-1 rounded border border-slate-600 py-2 text-xs"><RotateCcw size={13} /> RESET TWIN</button>
            </section>
            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h2 className="mb-1 text-xs font-bold tracking-wider text-cyan-300">WORKFLOW</h2>
              <div className="text-[11px] font-mono text-slate-300">{s.runState}</div>
              <div className="mt-1 h-2 rounded bg-slate-800"><div className="h-2 rounded bg-cyan-400 transition-all" style={{ width: `${Math.max(4, (STAGES.indexOf(s.runState) + 1) / STAGES.length * 100)}%` }} /></div>
            </section>
          </aside>

          <section className="col-span-12 lg:col-span-7">
            <div className="h-[520px] rounded-2xl border border-cyan-900 overflow-hidden bg-slate-950">
              {s.twin
                ? s.viewMode === '3d'
                  ? <SceneBoundary fallback={<div><p className="p-3 text-amber-300 text-sm">3D unavailable (WebGL) — 2D fallback shown. All functions remain available.</p><Twin2D twin={s.twin} /></div>}><TwinScene twin={s.twin} /></SceneBoundary>
                  : <Twin2D twin={s.twin} />
                : <div className="p-6 text-slate-400">Loading twin…</div>}
            </div>
            <div className="mt-2 flex gap-2 text-xs">
              <button onClick={() => s.set({ viewMode: s.viewMode === '3d' ? '2d' : '3d' })} className="rounded border border-slate-600 px-2 py-1">Toggle {s.viewMode === '3d' ? '2D (accessible)' : '3D'}</button>
              <span className="text-slate-500 py-1">Drag to orbit · scroll to zoom · click node to inspect · status also available as text in the asset list</span>
            </div>
            <section className="mt-3 max-h-56 overflow-auto rounded-xl border border-slate-800 bg-slate-900/60 p-3" aria-label="Event timeline">
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

          <aside className="col-span-12 lg:col-span-3 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
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

      {s.view === 'agents' && (
        <main className="p-6">
          <h1 className="text-2xl font-black text-cyan-200">Agent Collaboration</h1>
          <p className="text-sm text-slate-400 mt-1">Six specialised agents, one orchestrated state machine. Only the Investigator and Strategist use Meta Muse Spark; provider failure is shown honestly, never faked.</p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {AGENTS.map((a, i) => {
              const active = s.events.some((e) => e.agent === a.id)
              const decisions = s.results?.decisions.filter((d) => d.agent === a.id) ?? []
              return (
                <motion.section key={a.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                  className={`rounded-xl border p-4 ${active ? 'border-cyan-400 bg-cyan-950/40' : 'border-slate-800 bg-slate-900/60'}`}>
                  <div className="flex items-center gap-2"><Bot className="text-cyan-300" size={18} /><b>{a.name}</b>{active && <span className="text-[10px] text-emerald-300 font-mono">ACTIVE</span>}</div>
                  <p className="mt-1 text-xs text-slate-400">{a.desc}</p>
                  {decisions.map((d, j) => (
                    <div key={j} className="mt-2 rounded bg-slate-950/70 p-2 text-xs">
                      <div>{d.decision}</div>
                      <div className="text-slate-400 mt-1">{d.justification}</div>
                      <div className="font-mono text-[10px] mt-1 text-slate-500">confidence {(d.confidence * 100).toFixed(0)}% · {d.model} · mode={d.mode}</div>
                    </div>
                  ))}
                </motion.section>
              )
            })}
          </div>
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
              <div className="h-[360px] rounded-xl border border-cyan-900 overflow-hidden">{s.twin && <TwinScene twin={s.twin} />}</div>
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
                <section className="rounded-xl border border-red-900/60 bg-slate-900/60 p-4"><h2 className="font-bold text-red-300">BEFORE DEFENSE</h2>
                  <p className="text-sm mt-2">Attack objective reachable/granted: {String(s.results.verification.metrics.baseline_reachable_or_granted)}</p>
                  <p className="text-xs text-slate-400">Path: {(s.results.verification.metrics.baseline_path as string[] | null)?.join(' → ') ?? 'identity session'}</p></section>
                <section className="rounded-xl border border-emerald-900/60 bg-slate-900/60 p-4"><h2 className="font-bold text-emerald-300">AFTER DEFENSE</h2>
                  <p className="text-sm mt-2">Attack objective reachable/granted: {String(s.results.verification.metrics.after_reachable_or_granted)}</p>
                  <p className="text-xs text-slate-400">Path: {(s.results.verification.metrics.after_path as string[] | null)?.join(' → ') ?? 'none / denied'}</p></section>
              </div>
              <dl className="mt-4 grid gap-2 md:grid-cols-4 text-center">
                {[['Defense effectiveness', `${s.results.verification.metrics.defense_effectiveness_pct}%`],
                  ['Time to detect', `${s.results.verification.metrics.time_to_detect_s}s`],
                  ['Time to contain', `${s.results.verification.metrics.time_to_contain_s ?? '—'}s`],
                  ['Legit paths disrupted', `${s.results.verification.metrics.operational_impact_disrupted_legit_paths}`]].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><dt className="text-[11px] text-slate-400">{k}</dt><dd className="text-xl font-black text-cyan-200">{v}</dd></div>
                ))}
              </dl>
              <ul className="mt-4 space-y-1 text-sm">{s.results.verification.checks.map((c) => (
                <li key={c.name} className={c.passed ? 'text-emerald-300' : 'text-red-300'}>{c.passed ? '✓' : '✗'} {c.name} — <span className="text-slate-300">{c.detail}</span></li>))}
              </ul>
              <p className="mt-4 text-slate-300 font-semibold">CYBERGENESIS does not merely detect cyberattacks. It tests defenses and verifies resilience.</p>
            </div>
          )}
        </main>
      )}

      {s.view === 'evidence' && <EvidenceView />}
      {s.view === 'settings' && (
        <main className="p-6 max-w-2xl space-y-3 text-sm">
          <h1 className="text-2xl font-black text-cyan-200">System Settings</h1>
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-1">
            <div className="flex items-center gap-2"><Database size={15} /> Model: {s.modelStatus?.model} · Provider: Meta Model API</div>
            <div>Mode: <b>{s.modelStatus?.mode}</b> · Configured: {String(s.modelStatus?.configured)} · Reachable: {String(s.modelStatus?.reachable)}</div>
            <div className="text-slate-400">{s.modelStatus?.detail}</div>
            <div className="text-slate-500 text-xs">API keys are read from backend environment only and are never displayed. Set MODEL_API_KEY + restart backend for LIVE META AI; otherwise the app runs in clearly-labelled OFFLINE SIMULATION mode.</div>
          </div>
          <button onClick={() => void resetAll()} className="rounded bg-red-500/80 px-4 py-2 font-semibold text-white">Reset twin &amp; clear current run view</button>
          <button onClick={exportReport} disabled={!s.runId} className="ml-2 rounded border border-slate-600 px-4 py-2 disabled:opacity-40"><Download size={14} className="inline" /> Export report JSON</button>
        </main>
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
        <div key={i} className="rounded border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs"><span className="font-mono text-cyan-300">{e.event_type}</span> <span className="text-slate-300">{e.message}</span></div>
      ))}</div>
    </main>
  )
}
