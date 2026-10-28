import { useState } from 'react'
import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { api } from '../services/api'
import type { PreflightResult } from '../types'

const SAMPLE_OPS = JSON.stringify({ ops: [{ op: 'add_link', src: 'web-server', dst: 'database' }] }, null, 2)
const SAMPLE_CONFIG = 'hostname edge-fw\ninterface Gi0/0\n ip address 10.0.0.1/24\nline vty 0 4\n transport input telnet'

/** Attack-path regression preflight panel: paste ops or configs, replay on a clone. */
export function PreflightPanel() {
  const [twinId, setTwinId] = useState('builtin')
  const [mode, setMode] = useState<'ops' | 'configs'>('ops')
  const [text, setText] = useState(SAMPLE_OPS)
  const [result, setResult] = useState<PreflightResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    setBusy(true); setErr(null)
    try {
      const change = mode === 'ops' ? JSON.parse(text) : { configs: text, dialect: 'cisco_ios' }
      setResult(await api.preflight(twinId.trim() || 'builtin', change))
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e)); setResult(null)
    } finally { setBusy(false) }
  }

  return (
    <section className="mt-4 rounded-xl border border-slate-700 bg-slate-900/40 p-4" aria-label="Preflight a change">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck size={16} className="text-cyan-300" />
        <b className="text-slate-100">Preflight a change</b>
        <span className="text-xs text-slate-400">Replay a proposed change against every saved scenario on a clone. The stored twin is never mutated.</span>
      </div>
      <label className="mt-3 block text-xs text-slate-400">Twin id
        <input aria-label="Twin id" value={twinId} onChange={(e) => setTwinId(e.target.value)} className="ml-2 rounded bg-slate-800 px-2 py-1 text-slate-100" />
      </label>
      <div className="mt-2 flex gap-2 text-xs">
        <button onClick={() => { setMode('ops'); setText(SAMPLE_OPS) }} className={`rounded px-2 py-1 ${mode === 'ops' ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-300'}`}>Change ops (JSON)</button>
        <button onClick={() => { setMode('configs'); setText(SAMPLE_CONFIG) }} className={`rounded px-2 py-1 ${mode === 'configs' ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-300'}`}>Paste configs</button>
      </div>
      <textarea aria-label="Change input" value={text} onChange={(e) => setText(e.target.value)} rows={6}
        className="mt-2 w-full rounded bg-slate-950 p-2 font-mono text-xs text-slate-100" />
      <button onClick={run} disabled={busy} className="mt-2 rounded bg-cyan-600 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50">
        {busy ? 'Running…' : 'Run preflight'}
      </button>
      {err && <p className="mt-2 text-xs text-red-300">Preflight failed: {err}</p>}
      {result && (
        <div className="mt-3">
          <div className={`flex items-center gap-2 rounded px-3 py-2 font-bold ${result.verdict === 'PASS' ? 'bg-emerald-900/50 text-emerald-200' : 'bg-red-900/50 text-red-200'}`} role="status">
            {result.verdict === 'PASS' ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
            {result.verdict === 'PASS' ? 'PASS — no regression' : 'FAIL — regression detected'}
          </div>
          <p className="mt-1 text-[11px] text-slate-400">Derived ops: {JSON.stringify(result.change_ops)}</p>
          <table className="mt-2 w-full text-left text-xs">
            <thead><tr className="text-slate-400"><th>Scenario</th><th>Status</th><th>Before</th><th>After</th><th>New paths</th></tr></thead>
            <tbody>
              {result.results.map((r) => (
                <tr key={r.scenario_id} className={r.status === 'REGRESSION' ? 'text-red-300' : 'text-slate-200'}>
                  <td title={r.scenario_id}>{r.scenario_name || r.scenario_id}</td><td>{r.status}</td>
                  <td>{String(r.baseline_reachable)}</td><td>{String(r.after_reachable)}</td>
                  <td>{r.new_paths.length ? r.new_paths.map((p) => p.join(' → ')).join('; ') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.results.filter((r) => r.status === 'REGRESSION').map((r) => (
            <div key={`hl-${r.scenario_id}`} className="mt-2 rounded border border-red-800 bg-red-950/30 p-2 text-xs text-red-200">
              Regression path: {r.new_paths.map((p) => p.join(' → ')).join(' | ')}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
