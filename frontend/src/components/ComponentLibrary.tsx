import { useEffect, useState } from 'react'
import { Boxes, Shield, Swords } from 'lucide-react'
import { api } from '../services/api'
import type { Library, LibraryItem } from '../types'

function Section({ title, icon, items, render }: { title: string; icon: React.ReactNode; items: LibraryItem[]; render: (i: LibraryItem) => string }) {
  const [q, setQ] = useState('')
  const filtered = items.filter((i) => `${i.id} ${i.label} ${i.description}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="flex items-center gap-2 font-bold text-cyan-200">{icon} {title} <span className="text-xs text-slate-500">({filtered.length}/{items.length})</span></h2>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter…" aria-label={`Filter ${title}`} className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs" />
      <div className="mt-2 space-y-1">
        {filtered.map((i) => (
          <div key={i.id} className="rounded bg-slate-950/60 px-2 py-1.5 text-xs">
            <b className="font-mono text-cyan-300">{i.id}</b> · {i.label}
            <div className="text-slate-400">{i.description}</div>
            <div className="font-mono text-[10px] text-slate-500">{render(i)}</div>
          </div>
        ))}
        {filtered.length === 0 && <p className="text-xs text-slate-500">No matches.</p>}
      </div>
    </section>
  )
}

export default function ComponentLibrary() {
  const [lib, setLib] = useState<Library | null>(null)
  useEffect(() => { api.library().then(setLib).catch(() => undefined) }, [])
  if (!lib) return <main className="p-6 text-slate-400">Loading component library… (backend on :8000 required)</main>
  return (
    <main className="p-6">
      <h1 className="text-2xl font-black text-cyan-200">Component Library</h1>
      <p className="mt-1 text-sm text-slate-400">The browseable catalog behind the Twin Designer and Attack Playbook — served by <span className="font-mono">GET /api/library</span>. If it is not listed here, the policy engine will not run it.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Section title="Asset Types" icon={<Boxes size={16} />} items={lib.asset_types}
          render={(i) => `zone=${i.default_zone} · posture=${i.default_posture}`} />
        <Section title="Attack Steps (allowlisted)" icon={<Swords size={16} />} items={lib.attack_steps}
          render={() => 'synthetic telemetry only · no payloads'} />
        <Section title="Defense Actions (allowlisted)" icon={<Shield size={16} />} items={lib.defense_actions}
          render={(i) => i.params_contract ?? ''} />
      </div>
      <p className="mt-3 text-xs text-slate-500">Verification kinds: {lib.verification_kinds.join(', ')} · Zones: {lib.zones.join(', ')}</p>
    </main>
  )
}
