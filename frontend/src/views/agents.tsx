import { useEffect, useState } from 'react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { AgentMsg, Asset, RunResult, Twin, View } from '../types'

export const KIND_COLOR: Record<string, string> = {
  observation: '#22d3ee', hypothesis: '#a78bfa', proposal: '#38bdf8', critique: '#ef4444',
  finding: '#f59e0b', request: '#fb923c', decision: '#34d399', report: '#2dd4bf',
}
export const STAGES = ['SCENARIO_SELECTED', 'ATTACK_SIMULATING', 'TELEMETRY_COLLECTED', 'INVESTIGATING', 'DEFENSE_PROPOSED', 'POLICY_VALIDATING', 'DEFENSE_APPLYING', 'VERIFYING', 'COMPLETED']

export function ConversationMap({ messages }: { messages: AgentMsg[] }) {
  const [scrub, setScrub] = useState<number | null>(null)
  const [selected, setSelected] = useState<AgentMsg | null>(null)
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const shown = messages.slice(0, scrub ?? messages.length)
  const agents = [...new Set(messages.flatMap((m) => [m.from_agent, m.to_agent]).filter((x): x is string => Boolean(x)))]
  const teams = ['command', 'blue', 'red', 'assurance']
  const pos = new Map(agents.map((a, i) => [a, { x: 90 + (i % 5) * 150, y: 60 + Math.floor(i / 5) * 110 }]))
  return (
    <section className="mt-4 rounded-2xl border border-slate-800 glass-panel p-4" aria-label="Agent conversation map">
      <div className="flex items-center justify-between">
        <h2 className="font-bold text-cyan-200">Agent Conversation Map</h2>
        <span className="font-mono text-[10px] text-slate-500">{shown.length}/{messages.length} messages · teams: {teams.join(' · ')}</span>
      </div>
      {messages.length === 0 && <p className="mt-2 text-xs text-slate-500">No blackboard messages yet — run an experiment.</p>}
      <svg viewBox="0 0 820 260" className="mt-2 w-full" role="img" aria-label="Agent message graph">
        {shown.map((m, i) => {
          const from = pos.get(m.from_agent)
          const to = m.to_agent ? pos.get(m.to_agent) : undefined
          if (!from) return null
          const targets = to ? [to] : agents.filter((a) => a !== m.from_agent).map((a) => pos.get(a)!).filter(Boolean).slice(0, 3)
          return targets.map((t, j) => (
            <g key={`${m.id}-${j}`} onClick={() => setSelected(m)} style={{ cursor: 'pointer' }}>
              <line x1={from.x} y1={from.y} x2={t.x} y2={t.y} stroke={KIND_COLOR[m.kind] ?? '#64748b'} strokeWidth={1.4} opacity={0.65}
                strokeDasharray={reduced ? 'none' : '5 4'}>
                {!reduced && <animate attributeName="stroke-dashoffset" from="18" to="0" dur="1.2s" repeatCount="indefinite" />}
              </line>
              <circle cx={(from.x + t.x) / 2} cy={(from.y + t.y) / 2} r={3.5} fill={KIND_COLOR[m.kind] ?? '#64748b'} />
            </g>
          ))
        })}
        {agents.map((a) => {
          const p = pos.get(a)!
          return <g key={a}><circle cx={p.x} cy={p.y} r={17} fill="#0b2237" stroke="#22d3ee" />
            <text x={p.x} y={p.y + 30} textAnchor="middle" fill="#e2e8f0" fontSize={8.5} fontFamily="monospace">{a.replaceAll('_', ' ').slice(0, 18)}</text></g>
        })}
      </svg>
      <div className="flex items-center gap-2">
        <input type="range" min={0} max={messages.length} value={scrub ?? messages.length}
          onChange={(e) => setScrub(Number(e.target.value))} className="flex-1" aria-label="Scrub message timeline" />
        <span className="font-mono text-[10px] text-slate-400">{scrub ?? messages.length}/{messages.length}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        {Object.entries(KIND_COLOR).map(([k, c]) => <span key={k} className="font-mono text-[9px]" style={{ color: c }}>● {k}</span>)}
      </div>
      {selected && (
        <div className="mt-2 rounded bg-slate-950/80 p-2 text-xs">
          <b className="font-mono" style={{ color: KIND_COLOR[selected.kind] }}>{selected.kind}</b> {selected.from_agent} → {selected.to_agent ?? 'broadcast'}
          <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap text-[10px] text-slate-400">{JSON.stringify(selected.payload, null, 1)}</pre>
          {selected.evidence_refs.length > 0 && <p className="font-mono text-[10px] text-cyan-300">evidence: {selected.evidence_refs.join(', ')}</p>}
        </div>
      )}
    </section>
  )
}

export function CommanderPlanView() {
  const s = useStore()
  const ev = [...s.events].reverse().find((e) => e.event_type === 'commander_plan')
  const plan = (ev?.payload?.plan ?? []) as { step: number; agents: string[]; why: string }[]
  const finishedSteps = new Set(s.events.filter((e) => e.event_type === 'plan_step_finished').map((e) => (e.payload?.step as number)))
  const startedSteps = new Set(s.events.filter((e) => e.event_type === 'plan_step_started').map((e) => (e.payload?.step as number)))
  const stageIdx = Math.max(STAGES.indexOf(s.runState), 0)
  if (!ev) return null
  return (
    <section className="mt-4 rounded-2xl border border-violet-800/60 bg-violet-950/25 p-4" aria-label="Commander plan">
      <h2 className="font-bold text-violet-200">Commander Plan (validated DAG)</h2>
      <p className="text-[11px] text-slate-400">{ev.message}</p>
      <ol className="mt-2 space-y-1">
        {plan.map((p, i) => (
          <li key={p.step} className={`flex items-center gap-2 rounded px-2 py-1.5 text-xs ${startedSteps.has(p.step) && !finishedSteps.has(p.step) ? 'bg-violet-500/25 border border-violet-400 animate-pulse' : finishedSteps.has(p.step) || i < stageIdx ? 'text-emerald-300' : 'text-slate-300'}`}>
            <span className="font-mono">{finishedSteps.has(p.step) || i < stageIdx || s.runState === 'COMPLETED' ? '✓' : startedSteps.has(p.step) ? '▶ running' : '·'} step {p.step}</span>
            <b>{p.agents.join(' + ')}</b><span className="text-slate-500">{p.why}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}
