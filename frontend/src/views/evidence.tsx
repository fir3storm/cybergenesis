import { useEffect, useState } from 'react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { Asset, RunResult, Twin, View } from '../types'
export function EvidenceView() {
  const s = useStore()
  const [rows, setRows] = useState<{ id: string; kind: string; ref: string; summary: string }[] | null>(null)
  const load = () => { if (s.runId) api.evidence(s.runId).then(setRows).catch(() => undefined) }
  useEffect(() => { if (s.highlightRef) load() }, [s.highlightRef]) // eslint-disable-line
  return (
    <main className="p-6 max-w-4xl">
      <h1 className="text-2xl font-black text-cyan-200">Experiment Evidence</h1>
      <p className="text-sm text-slate-400">Append-only audit trail stored in the backend database. Clicking a ⌖ citation in the Agents view lands here with that record highlighted.</p>
      <div className="mt-3 flex gap-2">
        <button onClick={load} className="rounded bg-cyan-600 px-3 py-1.5 text-xs font-bold">Load evidence for current run</button>
        <button onClick={() => s.runId && api.report(s.runId).then((r) => {
          const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' })
          const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `cybergenesis-run-bundle-${s.runId}.json`; a.click()
        })} disabled={!s.runId} className="rounded border border-slate-600 px-3 py-1.5 text-xs disabled:opacity-40">Export run bundle (replayable JSON)</button>
        <label className="cursor-pointer rounded border border-slate-600 px-3 py-1.5 text-xs hover:bg-slate-800">
          Import run bundle
          <input type="file" accept="application/json" className="hidden" onChange={(e) => {
            const f = e.target.files?.[0]; if (!f) return
            f.text().then((txt) => {
              const bundle = JSON.parse(txt) as RunResult & { run?: RunResult['run'] }
              if (bundle.run?.id && bundle.verification !== undefined) {
                s.set({ results: bundle, runId: bundle.run.id, runState: bundle.run.state, error: null })
                setRows(null)
              }
            }).catch(() => s.set({ error: 'Invalid run bundle file' }))
          }} />
        </label>
      </div>
      {s.highlightRef && <p className="mt-2 text-xs text-cyan-300">Highlighting citation: <span className="font-mono">{s.highlightRef}</span></p>}
      <div className="mt-4 space-y-1">
        {(rows ?? s.events.map((e) => ({ id: '', kind: e.event_type, ref: '', summary: e.message }))).map((e, i) => (
          <div key={i} className={`rounded border px-3 py-2 text-xs ${s.highlightRef && e.ref === s.highlightRef ? 'border-amber-400 bg-amber-500/15' : 'border-slate-800 glass-panel'}`}>
            <span className="font-mono text-cyan-300">{e.kind}</span> {e.ref && <span className="font-mono text-slate-500">{e.ref}</span>} <span className="text-slate-300">{e.summary}</span>
          </div>
        ))}
      </div>
    </main>
  )
}
