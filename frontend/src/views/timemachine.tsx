import { useState } from 'react'
import { GitFork } from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { ForkResult, ForkSummary, Twin } from '../types'
import type { Candidate } from './panels'
import { Twin2D } from './twin'

const ROWS: [keyof ForkSummary, string, 'lower' | 'higher'][] = [
  ['effectiveness_pct', 'Effectiveness %', 'higher'],
  ['disrupted', 'Legit paths disrupted', 'lower'],
  ['risk_after_pct', 'Breach risk after %', 'lower'],
  ['users_affected', 'Users affected', 'lower'],
]
const ROUNDS_NOTE = 'The original column covers the whole run (every red-team round, final-round risk); the fork replays only the decision point once, so compare verdict, effectiveness and disruption most directly.'

function fmtDelta(v: number | undefined): string {
  if (v === undefined) return '—'
  return v > 0 ? `+${v}` : `${v}`
}

function TwinMini({ twin, title }: { twin?: Twin; title: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-2">
      <h3 className="text-[11px] font-bold text-slate-300">{title}</h3>
      {twin ? <Twin2D twin={twin} /> : <p className="p-2 text-[11px] text-slate-500">Twin unavailable from this server build.</p>}
    </div>
  )
}

function Timeline({ events, title }: { events?: { seq: number; event_type: string; message: string }[]; title: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-2" aria-label={title}>
      <h3 className="text-[11px] font-bold text-slate-300">{title}</h3>
      <ol className="mt-1 max-h-56 space-y-1 overflow-auto pr-1">
        {(events ?? []).map((e) => (
          <li key={e.seq} className="text-[11px] leading-snug text-slate-400">
            <span className="font-mono text-cyan-300">{e.event_type}</span> — {e.message}
          </li>
        ))}
        {!events?.length && <li className="text-[11px] text-slate-500">No timeline returned.</li>}
      </ol>
    </div>
  )
}

/** Counterfactual time machine: fork the finished run at its decision point with another candidate. */
export function TimeMachine() {
  const s = useStore()
  const cands = (s.results?.verification?.metrics.candidates as Candidate[] | undefined) ?? []
  const chosen = (s.results?.verification?.metrics.ai_final_choice as { chosen_label?: string } | undefined)?.chosen_label
  const forkedFrom = s.results?.verification?.metrics.forked_from as string | undefined
  const [res, setRes] = useState<ForkResult | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [err, setErr] = useState<string | null>(null)
  if (!s.runId || !cands.length || s.runState !== 'COMPLETED') return null

  const fork = (i: number) => {
    setBusy(i); setErr(null)
    api.fork(s.runId!, i).then(setRes).catch((e: Error) => setErr(e.message)).finally(() => setBusy(null))
  }
  const openFork = (id: string) => {
    Promise.all([api.results(id), api.events(id)]).then(([results, events]) =>
      s.set({ runId: id, results, events, runState: results.run.state }))
  }
  return (
    <section className="mt-4 rounded-xl border border-slate-700 bg-slate-900/60 p-4" aria-label="Counterfactual time machine">
      <h2 className="flex items-center gap-2 font-bold text-cyan-200"><GitFork size={16} /> Time machine — what if Blue had chosen differently?</h2>
      <p className="mt-1 text-xs text-slate-400">
        Forks this run at the decision point (the attacked snapshot), applies another simulated candidate through the same policy
        engine, and re-verifies. Deterministic — no AI call — and the original run is never changed.
        {forkedFrom && <> This run is itself a fork of <span className="font-mono">{forkedFrom}</span>.</>}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {cands.map((c, i) => (
          <button key={i} disabled={busy !== null || c.label === chosen} onClick={() => fork(i)}
            className="rounded border border-cyan-800 px-2 py-1 text-[11px] text-cyan-100 disabled:opacity-40"
            title={c.label === chosen ? 'This is what the run actually chose' : `Fork with: ${c.label}`}>
            {busy === i ? 'Forking…' : `${c.label === chosen ? '✓ ' : '⑂ '}${c.label}`}
          </button>
        ))}
      </div>
      {err && <p className="mt-2 text-xs text-red-300">Fork failed: {err}</p>}
      {res && (
        <div className="mt-3">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs" aria-label="Fork comparison">
              <thead><tr className="text-slate-400">
                <th className="py-1">Metric</th><th>Original ({res.original.actions.join(', ') || '—'})</th><th>Fork ({res.candidate})</th><th>Δ (fork − original)</th>
              </tr></thead>
              <tbody>
                <tr className="border-t border-slate-800"><td className="py-1">Verdict</td>
                  <td className={res.original.outcome === 'PASS' ? 'text-emerald-300' : 'text-red-300'}>{res.original.outcome ?? '—'}</td>
                  <td className={res.fork.outcome === 'PASS' ? 'text-emerald-300' : 'text-red-300'}>{res.fork.outcome ?? '—'}</td>
                  <td>{res.delta.verdict_changed ? 'changed' : 'same'}</td></tr>
                <tr className="border-t border-slate-800"><td className="py-1">Red-team rounds</td>
                  <td>{String(res.original.rounds ?? 1)}</td><td>{String(res.fork.rounds ?? 1)}</td><td>{fmtDelta(res.delta.rounds)}</td></tr>
                {ROWS.map(([k, label]) => (
                  <tr key={k} className="border-t border-slate-800"><td className="py-1">{label}</td>
                    <td>{String(res.original[k] ?? '—')}</td>
                    <td>{String(res.fork[k] ?? '—')}</td>
                    <td>{fmtDelta(res.delta[k as keyof typeof res.delta] as number | undefined)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-slate-400">{ROUNDS_NOTE}</p>
          <div className="mt-3 grid gap-3 lg:grid-cols-2" aria-label="Compare timelines and twins">
            <Timeline events={res.original_timeline} title="Original timeline" />
            <Timeline events={res.fork_timeline} title="Fork timeline" />
            <TwinMini twin={res.original_twin} title="Original twin (after defense)" />
            <TwinMini twin={res.fork_twin} title="Fork twin (after defense)" />
          </div>
          <button onClick={() => openFork(res.fork_id)} className="mt-3 rounded bg-cyan-700 px-3 py-1.5 text-xs font-bold text-white">Open fork run</button>
        </div>
      )}
    </section>
  )
}
