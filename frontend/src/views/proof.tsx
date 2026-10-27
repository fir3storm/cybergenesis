import { useEffect, useState } from 'react'
import { BadgeCheck, Download } from 'lucide-react'
import { api } from '../services/api'
import type { Certificate } from '../types'

function saveJson(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click()
}

/** Proof-carrying defense: download a signed certificate an outsider can verify without any LLM. */
export function ProofCard({ runId, outcome }: { runId: string | null; outcome: string | undefined }) {
  const [cert, setCert] = useState<Certificate | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const pass = Boolean(runId && outcome === 'PASS')
  useEffect(() => {
    if (!runId || outcome !== 'PASS') { setCert(null); return }
    let live = true
    api.getCertificate(runId).then((c) => { if (live) setCert(c) }).catch((e: Error) => { if (live) setErr(e.message) })
    return () => { live = false }
  }, [runId, outcome])
  if (!pass) return null
  const download = () => {
    setErr(null)
    if (cert) { saveJson(`certificate-${runId}.json`, cert); return }
    api.getCertificate(runId as string).then((c) => { setCert(c); saveJson(`certificate-${runId}.json`, c) })
      .catch((e: Error) => setErr(e.message))
  }
  const last = cert?.campaigns[cert.campaigns.length - 1]
  return (
    <section className="mt-4 rounded-xl border border-emerald-800/70 bg-emerald-950/20 p-4" aria-label="Proof certificate">
      <div className="flex flex-wrap items-center gap-2">
        <BadgeCheck size={16} className="text-emerald-300" />
        <b className="text-emerald-200">Proof-carrying defense</b>
        <span className="text-xs text-slate-400">The AI doesn't ask you to trust it — it hands you a proof.</span>
        <button onClick={download} className="ml-auto flex items-center gap-1 rounded bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white">
          <Download size={13} /> Download proof
        </button>
      </div>
      {err && <p className="mt-2 text-xs text-red-300">Certificate unavailable: {err}</p>}
      {cert && (
        <dl className="mt-3 grid gap-2 text-xs md:grid-cols-2">
          <div><dt className="text-slate-400">Signature (HMAC-SHA256)</dt><dd className="font-mono text-emerald-200">{cert.signature.slice(0, 24)}…</dd></div>
          <div><dt className="text-slate-400">Event hash chain ({cert.events_count} events)</dt><dd className="font-mono text-emerald-200">{cert.event_hash_chain.slice(0, 24)}…</dd></div>
          <div><dt className="text-slate-400">Campaigns replayed</dt><dd className="text-slate-200">{cert.campaigns.length} · min-cut {cert.min_cut_edges} edge(s)</dd></div>
          <div><dt className="text-slate-400">Target reachable after defense</dt>
            <dd className={last?.unreachable_proof.target_reachable ? 'text-red-300' : 'text-emerald-300'}>
              {String(last?.unreachable_proof.target_reachable ?? '—')} · {last?.unreachable_proof.frontier.length ?? 0} blocked frontier arc(s)</dd></div>
        </dl>
      )}
      <p className="mt-2 font-mono text-[11px] text-slate-400">Verify locally: python scripts/verify_cert.py certificate-{runId}.json</p>
    </section>
  )
}
