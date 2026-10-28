import { useEffect, useState } from 'react'
import { Briefcase, Download, Sparkles, Volume2 } from 'lucide-react'
import { api } from '../services/api'
import type { Briefing } from '../types'

/** One-page CISO board briefing: verified facts, decisions requested, control evidence. */
export function BriefingCard({ runId, outcome }: { runId: string | null; outcome: string | undefined }) {
  const [b, setB] = useState<Briefing | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    setB(null); setErr(null)
    if (!runId || !outcome) return
    let live = true
    api.briefing(runId, false).then((r) => { if (live) setB(r) }).catch((e: Error) => { if (live) setErr(e.message) })
    return () => { live = false }
  }, [runId, outcome])
  if (!runId || !outcome) return null

  const narrate = () => {
    setBusy(true); setErr(null)
    api.briefing(runId, true).then(setB).catch((e: Error) => setErr(e.message)).finally(() => setBusy(false))
  }
  const speak = () => {
    if (!b || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const text = `${b.narrative.headline} ${b.narrative.summary} Decisions requested: ${b.narrative.board_asks.join('. ')}`
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
  }
  const download = () => {
    api.briefingMarkdown(runId, b?.narrative.mode === 'live').then((md) => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([md], { type: 'text/markdown' })); a.download = `board-briefing-${runId}.md`; a.click()
    }).catch((e: Error) => setErr(e.message))
  }
  const n = b?.narrative
  return (
    <section className="mt-4 rounded-xl border border-amber-800/70 bg-amber-950/10 p-4" aria-label="Board briefing">
      <div className="flex flex-wrap items-center gap-2">
        <Briefcase size={16} className="text-amber-300" />
        <b className="text-amber-200">Board briefing</b>
        {n && <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${n.mode === 'live' ? 'bg-violet-700 text-white' : 'bg-slate-700 text-slate-200'}`}>
          {n.mode === 'live' ? `AI-DRAFTED · ${n.model}` : 'DETERMINISTIC'}</span>}
        <div className="ml-auto flex gap-1">
          <button onClick={narrate} disabled={busy} className="flex items-center gap-1 rounded border border-violet-600 px-2 py-1 text-[11px] text-violet-200 disabled:opacity-50">
            <Sparkles size={12} /> {busy ? 'Drafting…' : 'Draft with AI'}</button>
          <button onClick={speak} disabled={!b} className="flex items-center gap-1 rounded border border-slate-600 px-2 py-1 text-[11px]" aria-label="Read briefing aloud"><Volume2 size={12} /> Read aloud</button>
          <button onClick={download} disabled={!b} className="flex items-center gap-1 rounded bg-amber-600 px-2 py-1 text-[11px] font-bold text-slate-950"><Download size={12} /> .md</button>
        </div>
      </div>
      {err && <p className="mt-2 text-xs text-red-300">Briefing unavailable: {err}</p>}
      {n?.fallback_reason && <p className="mt-2 text-[11px] text-amber-300">AI narrative unavailable, showing the deterministic summary: {n.fallback_reason}</p>}
      {b && n && (
        <>
          <p className="mt-2 text-sm font-bold text-slate-100">{n.headline}</p>
          <p className="mt-1 text-xs text-slate-300">{n.summary}</p>
          <h3 className="mt-2 text-[11px] font-bold tracking-wider text-amber-300">DECISIONS REQUESTED</h3>
          <ul className="list-disc pl-5 text-xs text-slate-300">{n.board_asks.map((a) => <li key={a}>{a}</li>)}</ul>
          <h3 className="mt-2 text-[11px] font-bold tracking-wider text-amber-300">CONTROL EVIDENCE</h3>
          <div className="mt-1 flex flex-wrap gap-1">
            {b.compliance.map((t) => (
              <span key={t.id} title={`${t.title}${t.title ? ' — ' : ''}evidenced by ${t.evidenced_by.join(', ')}`}
                className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-200">
                {t.framework === 'NIST CSF 2.0' ? `CSF ${t.id}` : t.id}
              </span>
            ))}
          </div>
          <p className="mt-2 text-[10px] text-slate-500">{b.disclaimer}</p>
        </>
      )}
    </section>
  )
}
