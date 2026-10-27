import { useEffect, useState } from 'react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { Asset, RunResult, Twin, View } from '../types'
import { STATUS_COLOR } from '../components/status'

export interface Candidate { label: string; origin: string; blocked: boolean; disrupted: number | null; feasible: boolean; detail: string }
export interface Round { round: number; path: string[] | null; effectiveness_pct: number; resilience_score?: number; outcome: string; red_team_mode: string | null }

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
      {m?.ai_final_choice != null && (
        <p className="mt-1 text-[11px] text-violet-300">
          AI final choice: {String((m.ai_final_choice as { chosen_label?: string }).chosen_label ?? '—')}
          {' '}· matched simulation optimum: {m.ai_matched_optimum === true ? 'yes' : m.ai_matched_optimum === false ? 'no (AI chose differently — its justification is in the timeline)' : '—'}
          {' '}· candidates considered: {String(m.candidates_considered ?? '—')}
        </p>
      )}
    </section>
  )
}

export function ResilienceCurve() {
  const s = useStore()
  const rounds = (s.results?.verification?.metrics.rounds as Round[] | undefined) ?? []
  if (!rounds.length) return null
  const score = (r: Round) => r.resilience_score ?? r.effectiveness_pct
  const pts = rounds.map((r, i) => `${30 + i * 90},${90 - (score(r) / 100) * 70}`).join(' ')
  const offline = s.results?.run.mode !== 'live'
  return (
    <section className="mt-4 rounded-xl border border-slate-800 glass-panel p-4">
      <h2 className="font-bold text-cyan-200">Resilience Curve — Red Team Rounds</h2>
      {offline && <p className="mt-1 rounded border border-amber-700/60 bg-amber-950/30 px-2 py-1 text-[11px] text-amber-200">Adaptive adversary path-choice by Muse Spark requires LIVE Meta AI — this run used the deterministic (shortest-path) red team. Paths themselves are always policy-validated.</p>}
      <svg viewBox={`0 0 ${60 + rounds.length * 90} 110`} className="mt-2 w-full max-w-md" role="img" aria-label="Resilience curve over red-team rounds">
        <line x1={25} y1={15} x2={25} y2={92} stroke="#334155" /><line x1={25} y1={92} x2={55 + rounds.length * 90} y2={92} stroke="#334155" />
        <polyline points={pts} fill="none" stroke="#34d399" strokeWidth={2.5} />
        {rounds.map((r, i) => <g key={r.round}><circle cx={30 + i * 90} cy={90 - (score(r) / 100) * 70} r={5} fill={r.outcome === 'PASS' ? '#34d399' : '#ef4444'} />
          <text x={30 + i * 90} y={106} textAnchor="middle" fill="#94a3b8" fontSize={9}>R{r.round} · {score(r)}%</text></g>)}
      </svg>
      {rounds.map((r) => <p key={r.round} className="text-xs text-slate-300">Round {r.round}: {r.path ? r.path.join(' → ') : 'initial attack'} → {r.outcome} <span className="text-slate-500">(resilience {score(r)}%{r.red_team_mode ? `, red team ${r.red_team_mode}` : ''})</span></p>)}
    </section>
  )
}

export function BattlePanel() {
  const s = useStore()
  const red = s.events.filter((e) => e.agent === 'adversary_simulator')
  const blue = s.results?.decisions.filter((d) => d.agent !== 'observer' && d.agent !== 'adversary_simulator') ?? []
  if (!red.length && !blue.length) return null
  return (
    <section className="rounded-xl border border-slate-800 glass-panel p-3">
      <h2 className="mb-2 text-xs font-bold tracking-wider text-cyan-300">RED vs BLUE</h2>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded bg-red-950/30 border border-red-900/50 p-2">
          <h3 className="text-[11px] font-bold text-red-300">🔴 RED — ADAPTIVE ADVERSARY</h3>
          {red.slice(-5).map((e, i) => <p key={i} className="mt-1 text-[10px] text-slate-300">{e.message.slice(0, 130)}</p>)}
          {!red.length && <p className="text-[10px] text-slate-500">No red activity yet.</p>}
        </div>
        <div className="rounded bg-cyan-950/30 border border-cyan-900/50 p-2">
          <h3 className="text-[11px] font-bold text-cyan-300">🔵 BLUE — DEFENSE</h3>
          {blue.slice(-5).map((d, i) => <p key={i} className="mt-1 text-[10px] text-slate-300"><span className="text-violet-300">{d.agent}:</span> {d.decision.slice(0, 110)}</p>)}
          {!blue.length && <p className="text-[10px] text-slate-500">No blue decisions yet.</p>}
        </div>
      </div>
    </section>
  )
}
