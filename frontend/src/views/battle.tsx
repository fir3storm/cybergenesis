import { useEffect, useState } from 'react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { Asset, RunResult, Twin, View } from '../types'
import { TwinView, AttackChain, SkeletonTwin } from './twin'
export function BattleView({ onRunBattle }: { onRunBattle: () => void }) {
  const s = useStore()
  const rounds = (s.results?.verification?.metrics.rounds as { round: number }[] | undefined) ?? []
  const red = s.events.filter((e) => ['adversary_simulator'].includes(e.agent ?? '') || ['red_critic', 'debate', 'decoy_tripped', 'red_team', 'red_team_pivot'].includes(e.event_type))
  const blue = s.events.filter((e) => ['incident_investigator', 'defense_strategist', 'defense_executor'].includes(e.agent ?? ''))
  const debates = s.events.filter((e) => e.event_type === 'debate' || e.event_type === 'red_critic')
  return (
    <main className="p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div>
          <h1 className="text-2xl font-black text-cyan-200">Battle — Red vs Blue</h1>
          <p className="text-xs text-slate-400">Adaptive adversary on the left, defense on the right, the twin in the middle. Round {Math.max(rounds.length, s.runState === 'IDLE' ? 0 : 1)} · state {s.runState}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => { s.set({ scenarioId: 'red_vs_blue_battle' }); onRunBattle() }} className="rounded-lg bg-red-500 px-4 py-2 text-sm font-bold text-white">⚔ Run Battle</button>
          <button onClick={() => s.set({ view: 'verification' })} className="rounded-lg border border-slate-600 px-3 py-2 text-sm">Resilience Curve →</button>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-12 gap-3">
        <section className="col-span-12 lg:col-span-3 space-y-2" aria-label="Red team reasoning">
          <h2 className="text-xs font-bold tracking-wider text-red-300">🔴 RED — CAMPAIGNS & CRITIC</h2>
          {red.length === 0 && <p className="text-xs text-slate-500">No red activity yet. Run the battle.</p>}
          {[...red].reverse().slice(0, 10).map((e, i) => (
            <div key={i} className="rounded-xl border border-red-900/50 bg-red-950/25 p-2 text-[11px] text-slate-200">
              <span className="font-mono text-red-300">{e.event_type}</span> — {e.message.slice(0, 220)}
            </div>
          ))}
          {debates.map((e, i) => (
            <div key={i} className="rounded-2xl rounded-tl-sm border border-violet-700/60 bg-violet-950/40 p-2 text-[11px] text-violet-100">💬 {e.message.slice(0, 220)}</div>
          ))}
        </section>
        <section className="col-span-12 lg:col-span-6">
          <div className="h-[560px] rounded-2xl border border-cyan-900 overflow-hidden bg-slate-950">
            {s.twin ? <TwinView twin={s.twin} /> : <SkeletonTwin />}
          </div>
          <AttackChain />
        </section>
        <section className="col-span-12 lg:col-span-3 space-y-2" aria-label="Blue team reasoning">
          <h2 className="text-xs font-bold tracking-wider text-cyan-300">🔵 BLUE — INVESTIGATE · SIMULATE · DEFEND</h2>
          {blue.length === 0 && <p className="text-xs text-slate-500">No blue activity yet.</p>}
          {[...blue].reverse().slice(0, 10).map((e, i) => (
            <div key={i} className="rounded-xl border border-cyan-900/50 bg-cyan-950/25 p-2 text-[11px] text-slate-200">
              <span className="font-mono text-cyan-300">{e.event_type}</span>{e.agent && <span className="text-violet-300"> · {e.agent}</span>} — {e.message.slice(0, 220)}
            </div>
          ))}
        </section>
      </div>
    </main>
  )
}
