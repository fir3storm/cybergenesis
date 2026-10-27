import { useEffect, useState } from 'react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { Asset, RunResult, Twin, View } from '../types'
function BenchmarkRunner() {
  const [status, setStatus] = useState('')
  const run = () => {
    setStatus('starting…')
    api.benchmarkRun(20, 7).then(async (r) => {
      for (let i = 0; i < 160; i++) {
        const st = await api.benchmarkStatus(r.run_id)
        setStatus(`${st.state} ${st.done}/${st.total} pairs`)
        if (st.state === 'COMPLETED') { setStatus('Benchmark complete — table above refreshes on next /api/benchmark read.'); break }
        if (st.state === 'FAILED') break
        await new Promise((res) => setTimeout(res, 900))
      }
    }).catch((e) => setStatus(`failed: ${(e as Error).message}`))
  }
  return (
    <div className="mt-3 flex items-center gap-2">
      <button onClick={run} className="rounded bg-cyan-600 px-3 py-2 text-xs font-bold">Run fresh benchmark (n=20)</button>
      <span className="text-xs text-slate-400">{status}</span>
      <a href="http://localhost:8000/api/benchmark" target="_blank" rel="noreferrer" className="text-xs text-cyan-300 underline">raw JSON</a>
    </div>
  )
}

export function BenchmarkView() {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.benchmark>> | null>(null)
  const [curve, setCurve] = useState<Awaited<ReturnType<typeof api.learningCurve>> | null>(null)
  const [cal, setCal] = useState<Awaited<ReturnType<typeof api.calibration>> | null>(null)
  useEffect(() => { api.benchmark().then(setData).catch(() => setData({ available: false, detail: 'benchmark endpoint unreachable' })) }, [])
  useEffect(() => { api.learningCurve().then(setCurve).catch(() => undefined); api.calibration().then(setCal).catch(() => undefined) }, [])
  return (
    <main className="p-6 max-w-4xl">
      <h1 className="text-2xl font-black text-cyan-200">Benchmark</h1>
      <p className="mt-1 text-sm text-slate-400">50 seeded random twin+scenario pairs, three defenders on identical attacked twins. Reproduce with <span className="font-mono">python scripts/benchmark.py</span>.</p>
      <BenchmarkRunner />
      {!data && <p className="mt-3 text-slate-400">Loading…</p>}
      {data && !data.available && <p className="mt-3 text-amber-300">{data.detail}</p>}
      {data?.summary && (
        <>
          <p className="mt-2 text-xs text-slate-500">{data.scope} · {data.pairs} pairs</p>
          <table className="mt-3 w-full text-left text-sm">
            <thead><tr className="border-b border-slate-700 text-slate-400"><th className="py-2">Defender</th><th>PASS rate</th><th>Mean effectiveness</th><th>Mean optimality gap</th><th>Mean disrupted</th></tr></thead>
            <tbody>{Object.entries(data.summary).map(([k, v]) => (
              <tr key={k} className="border-b border-slate-800"><td className="py-2 font-mono">{k}</td><td>{v.pass_rate_pct}%</td><td>{v.mean_effectiveness_pct}%</td><td>{v.mean_optimality_gap}</td><td>{v.mean_disrupted}</td></tr>))}
            </tbody>
          </table>
          <div className="mt-4 space-y-1" role="img" aria-label="Pass rate chart">
            {Object.entries(data.summary).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-xs"><span className="w-20 font-mono">{k}</span>
                <div className="h-4 flex-1 rounded bg-slate-800"><div className={`h-4 rounded ${k === 'none' ? 'bg-red-500' : 'bg-emerald-400'}`} style={{ width: `${v.pass_rate_pct}%` }} /></div><span>{v.pass_rate_pct}%</span></div>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">Live Muse Spark is spot-checked on the builtin scenarios (all PASS, gap 0 — see Verification Lab on any live run). The 50-pair table is a real offline run, not a projection.</p>
          {data.calibration && (
            <div className="mt-4 rounded-xl border border-slate-800 glass-panel p-3 text-sm">
              <b className="text-cyan-200">Confidence calibration</b> <span className="text-slate-400">({data.calibration.runs_scored} scored runs from the evidence store)</span>
              <p className="mt-1 text-xs text-slate-300">Mean Investigator confidence on PASS runs: {data.calibration.mean_confidence_pass ?? '—'} · on FAIL runs: {data.calibration.mean_confidence_fail ?? '—'}</p>
              <p className="text-[11px] text-slate-500">{data.calibration.note}</p>
            </div>
          )}
          <CompareRuns />
          {curve && curve.points.length > 0 && (
            <div className="mt-4 rounded-xl border border-slate-800 glass-panel p-3">
              <b className="text-cyan-200 text-sm">Learning curve — optimality gap over runs</b>
              <div className="mt-2 flex items-end gap-1" role="img" aria-label="Optimality gap per run">
                {curve.points.slice(-24).map((p, i) => (
                  <div key={i} title={`${p.scenario_id} (${p.mode}): gap ${p.optimality_gap ?? '—'}`}
                    className={`w-3 rounded-t ${p.outcome === 'PASS' ? 'bg-emerald-400' : 'bg-red-400'}`}
                    style={{ height: `${8 + Math.min((p.optimality_gap ?? 0) * 14, 56)}px` }} />
                ))}
              </div>
              <p className="mt-1 text-[11px] text-slate-500">{curve.runs} completed runs · bar height = optimality gap · green = PASS. Past verified defenses are fed back to the Strategist as examples.</p>
            </div>
          )}
          {cal && (
            <div className="mt-4 rounded-xl border border-slate-800 glass-panel p-3">
              <b className="text-cyan-200 text-sm">Confidence calibration (5 buckets)</b>
              <div className="mt-2 space-y-1">
                {cal.buckets.map((b) => (
                  <div key={b.bucket} className="flex items-center gap-2 text-xs"><span className="w-16 font-mono">{b.bucket}</span>
                    <div className="h-3 flex-1 rounded bg-slate-800"><div className="h-3 rounded bg-cyan-400" style={{ width: `${b.pass_rate_pct ?? 0}%` }} /></div>
                    <span>{b.pass_rate_pct === null ? `n=${b.n} (no data)` : `${b.pass_rate_pct}% PASS (n=${b.n})`}</span></div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </main>
  )
}

function CompareRuns() {
  const [runs, setRuns] = useState<{ id: string; scenario_id: string; state: string; mode: string }[]>([])
  const [a, setA] = useState(''); const [b, setB] = useState('')
  const [res, setRes] = useState<Record<string, RunResult>>({})
  useEffect(() => { api.experiments().then(setRuns).catch(() => undefined) }, [])
  const load = (id: string) => { if (id) api.results(id).then((r) => setRes((prev) => ({ ...prev, [id]: r }))).catch(() => undefined) }
  const cell = (id: string) => {
    const r = res[id]; if (!r) return '—'
    return `${r.run.mode} · ${r.verification?.outcome ?? r.run.state} · eff ${String(r.verification?.metrics.defense_effectiveness_pct ?? '—')}% · gap ${String(r.verification?.metrics.optimality_gap ?? '—')} · breach risk ${String(r.verification?.metrics.baseline_breach_probability_pct ?? '—')}% → ${String(r.verification?.metrics.after_breach_probability_pct ?? '—')}%`
  }
  const sel = 'rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs'
  return (
    <div className="mt-4 rounded-xl border border-slate-800 glass-panel p-3">
      <b className="text-cyan-200 text-sm">Compare runs side by side</b>
      <div className="mt-2 flex flex-wrap gap-2">
        <select value={a} onChange={(e) => { setA(e.target.value); load(e.target.value) }} className={sel}><option value="">Run A…</option>{runs.map((r) => <option key={r.id} value={r.id}>{r.scenario_id} · {r.mode} · {r.state}</option>)}</select>
        <select value={b} onChange={(e) => { setB(e.target.value); load(e.target.value) }} className={sel}><option value="">Run B…</option>{runs.map((r) => <option key={r.id} value={r.id}>{r.scenario_id} · {r.mode} · {r.state}</option>)}</select>
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-2 text-xs">
        <div className="rounded bg-slate-950/60 p-2"><b>A</b><p className="mt-1 text-slate-300">{cell(a)}</p></div>
        <div className="rounded bg-slate-950/60 p-2"><b>B</b><p className="mt-1 text-slate-300">{cell(b)}</p></div>
      </div>
    </div>
  )
}

export function ScorecardsView() {
  const [latest, setLatest] = useState<Awaited<ReturnType<typeof api.evalLatest>> | null>(null)
  const [status, setStatus] = useState('')
  const load = () => api.evalLatest().then(setLatest).catch(() => undefined)
  useEffect(() => { load() }, [])
  const run = (mode: string) => {
    setStatus(`running ${mode} eval…`)
    api.evalRun(10, 7, mode).then(async (r) => {
      for (let i = 0; i < 120; i++) {
        const st = await api.evalStatus(r.run_id)
        setStatus(`${st.state} ${st.done}/${st.total}`)
        if (st.state === 'COMPLETED') { load(); break }
        if (st.state === 'FAILED') break
        await new Promise((res) => setTimeout(res, 800))
      }
    }).catch((e) => setStatus(`failed: ${(e as Error).message}`))
  }
  const agents = latest?.result?.agents ?? {}
  return (
    <main className="p-6 max-w-5xl">
      <h1 className="text-2xl font-black text-cyan-200">Agent Scorecards</h1>
      <p className="mt-1 text-sm text-slate-400">Ground-truth evaluation over generated twins (investigator precision/recall, strategist pass rate + optimality, red validity, auditor precision/recall, identity recall, decoy trips, dialect parsing, citation validity, calibration).</p>
      <div className="mt-3 flex gap-2">
        <button onClick={() => run('offline')} className="rounded bg-cyan-600 px-3 py-2 text-xs font-bold">Run offline eval (n=10)</button>
        <button onClick={() => run('live')} className="rounded bg-violet-600 px-3 py-2 text-xs font-bold">Run live eval</button>
        <span className="py-2 text-xs text-slate-400">{status}</span>
      </div>
      {!latest?.available && <p className="mt-3 text-slate-500 text-sm">No eval yet — run one.</p>}
      {Object.entries(agents).map(([id, metrics]) => (
        <div key={id} className="mt-3 rounded-xl border border-slate-800 glass-panel p-3">
          <b className="font-mono text-cyan-200">{id}</b> <span className="text-xs text-slate-500">mode: {latest?.result?.mode}</span>
          <div className="mt-1 flex flex-wrap gap-1">
            {Object.entries(metrics).map(([k, v]) => (
              <span key={k} className="rounded bg-slate-950/70 px-2 py-1 font-mono text-[10px] text-slate-300">{k}: {String(v)}</span>
            ))}
          </div>
        </div>
      ))}
      {latest?.result?.calibration && Object.entries(latest.result.calibration).map(([agent, buckets]) => (
        <div key={agent} className="mt-3 rounded-xl border border-slate-800 glass-panel p-3">
          <b className="text-sm text-cyan-200">Calibration — {agent}</b>
          {buckets.map((b) => (
            <div key={b.bucket} className="mt-1 flex items-center gap-2 text-xs"><span className="w-16 font-mono">{b.bucket}</span>
              <div className="h-3 flex-1 rounded bg-slate-800"><div className="h-3 rounded bg-cyan-400" style={{ width: `${(b.accuracy ?? 0) * 100}%` }} /></div>
              <span>{b.accuracy === null ? `n=${b.n}` : `${Math.round((b.accuracy ?? 0) * 100)}% (n=${b.n})`}</span></div>
          ))}
        </div>
      ))}
    </main>
  )
}
