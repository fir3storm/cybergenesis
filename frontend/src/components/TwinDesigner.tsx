import { useEffect, useRef, useState } from 'react'
import { MousePointer2, Play, Plus, Save, Trash2, Waypoints } from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { Library } from '../types'

interface DAsset { id: string; name: string; asset_type: string; zone: string; posture: number; pos: [number, number, number]; vulnerabilities: string[] }
interface DConn { source: string; target: string; trust: string; traversable: boolean; types: string[] }

const sx = (x: number) => ((x + 9) / 18) * 720
const sy = (z: number) => ((z + 6) / 12) * 400
const wx = (px: number) => (px / 720) * 18 - 9
const wz = (py: number) => (py / 400) * 12 - 6

export default function TwinDesigner() {
  const { set, customTwins } = useStore()
  const [lib, setLib] = useState<Library | null>(null)
  const [name, setName] = useState('My Custom Twin')
  const [assets, setAssets] = useState<DAsset[]>([])
  const [conns, setConns] = useState<DConn[]>([])
  const [connectFrom, setConnectFrom] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const drag = useRef<{ id: string } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const counter = useRef(0)

  const refresh = () => api.customTwins().then((t) => set({ customTwins: t })).catch(() => undefined)
  useEffect(() => { api.library().then(setLib).catch(() => undefined); void refresh() }, []) // eslint-disable-line

  function addAsset(typeId: string) {
    const t = lib?.asset_types.find((a) => a.id === typeId)
    counter.current += 1
    const n = counter.current
    const id = `${typeId.replace('_', '-')}-${n}`
    const angle = n * 1.1
    setAssets([...assets, {
      id, name: `${t?.label ?? typeId} ${n}`, asset_type: typeId, zone: t?.default_zone ?? 'custom',
      posture: t?.default_posture ?? 0.7, vulnerabilities: [],
      pos: [Math.round(Math.cos(angle) * 5 * 10) / 10, 1.1, Math.round(Math.sin(angle) * 3.5 * 10) / 10],
    }])
  }

  function onNodeClick(id: string) {
    if (!connectFrom) { setConnectFrom(id); setMsg(`Connect mode: click a second asset to link from ${id} (click again to cancel)`) ; return }
    if (connectFrom === id) { setConnectFrom(null); return }
    if (!conns.some((c) => (c.source === connectFrom && c.target === id) || (c.source === id && c.target === connectFrom))) {
      setConns([...conns, { source: connectFrom, target: id, trust: 'medium', traversable: true, types: ['network'] }])
    }
    setConnectFrom(null); setMsg(null)
  }

  function onMove(e: React.PointerEvent) {
    if (!drag.current || !svgRef.current) return
    const r = svgRef.current.getBoundingClientRect()
    const x = wx(((e.clientX - r.left) / r.width) * 720)
    const z = wz(((e.clientY - r.top) / r.height) * 400)
    setAssets(assets.map((a) => a.id === drag.current!.id
      ? { ...a, pos: [Math.round(x * 10) / 10, a.pos[1], Math.round(z * 10) / 10] } : a))
  }

  async function save() {
    try {
      const saved = await api.createCustomTwin({ name, description: 'Designed in Twin Designer', assets, connections: conns })
      setMsg(`Saved twin "${saved.name}" (${saved.id}). Activate it or use it in the Attack Playbook.`)
      void refresh()
    } catch (e) { setMsg(`Save failed: ${(e as Error).message} — a twin needs ≥2 assets and valid connections.`) }
  }

  async function activate(id: string) {
    try { const r = await api.activateCustomTwin(id); set({ twin: r.twin, designerTwinId: id, view: 'twin' }) }
    catch (e) { setMsg(`Activate failed: ${(e as Error).message}`) }
  }

  return (
    <main className="p-6">
      <h1 className="text-2xl font-black text-cyan-200">Twin Designer</h1>
      <p className="mt-1 text-sm text-slate-400">Build a custom synthetic infrastructure: add assets from the library, drag them into place, click two assets to connect them, then save and activate. The same policy + verification engine runs on your twin.</p>
      {msg && <div className="mt-3 rounded border border-cyan-800 bg-slate-900 px-3 py-2 text-sm text-cyan-200">{msg}</div>}
      <div className="mt-4 grid gap-4 lg:grid-cols-12">
        <section className="lg:col-span-3 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <h2 className="text-xs font-bold tracking-wider text-cyan-300">COMPONENT PALETTE</h2>
          <div className="mt-2 space-y-1">
            {lib?.asset_types.map((a) => (
              <button key={a.id} onClick={() => addAsset(a.id)} className="flex w-full items-center gap-1 rounded bg-slate-800/70 px-2 py-1.5 text-left text-xs hover:bg-slate-700">
                <Plus size={12} /> {a.label} <span className="text-slate-500">({a.default_zone})</span>
              </button>
            ))}
          </div>
          <h2 className="mt-4 text-xs font-bold tracking-wider text-cyan-300">ASSETS ({assets.length})</h2>
          {assets.map((a) => (
            <div key={a.id} className="mt-1 flex items-center justify-between rounded bg-slate-950/60 px-2 py-1 text-xs">
              <span>{a.name} <span className="text-slate-500">{a.id}</span></span>
              <button aria-label={`delete ${a.id}`} onClick={() => { setAssets(assets.filter((x) => x.id !== a.id)); setConns(conns.filter((c) => c.source !== a.id && c.target !== a.id)) }}><Trash2 size={12} className="text-red-300" /></button>
            </div>
          ))}
          <h2 className="mt-4 text-xs font-bold tracking-wider text-cyan-300">CONNECTIONS ({conns.length})</h2>
          {conns.map((c, i) => (
            <div key={i} className="mt-1 flex items-center justify-between rounded bg-slate-950/60 px-2 py-1 text-xs">
              <span>{c.source} → {c.target}</span>
              <button aria-label="delete connection" onClick={() => setConns(conns.filter((_, j) => j !== i))}><Trash2 size={12} className="text-red-300" /></button>
            </div>
          ))}
        </section>

        <section className="lg:col-span-6">
          <svg ref={svgRef} viewBox="0 0 720 400" className="w-full rounded-xl border border-cyan-900 bg-[#04101f]"
            onPointerMove={onMove} onPointerUp={() => { drag.current = null }} role="img" aria-label="Twin design canvas. Assets are also listed as text on the left.">
            {Array.from({ length: 13 }, (_, i) => <line key={`v${i}`} x1={i * 60} y1={0} x2={i * 60} y2={400} stroke="#0e2a3f" />)}
            {Array.from({ length: 9 }, (_, i) => <line key={`h${i}`} x1={0} y1={i * 50} x2={720} y2={i * 50} stroke="#0e2a3f" />)}
            {conns.map((c, i) => {
              const a = assets.find((x) => x.id === c.source); const b = assets.find((x) => x.id === c.target)
              if (!a || !b) return null
              return <line key={i} x1={sx(a.pos[0])} y1={sy(a.pos[2])} x2={sx(b.pos[0])} y2={sy(b.pos[2])} stroke="#155e75" strokeWidth={2} />
            })}
            {assets.map((a) => (
              <g key={a.id} transform={`translate(${sx(a.pos[0])},${sy(a.pos[2])})`}
                onPointerDown={() => { drag.current = { id: a.id } }} onClick={() => onNodeClick(a.id)} style={{ cursor: 'grab' }}>
                <circle r={17} fill={connectFrom === a.id ? '#f59e0b' : '#0e7490'} stroke="#22d3ee" strokeWidth={connectFrom === a.id ? 3 : 1.5} />
                <text textAnchor="middle" dy={4} fill="#e0f2fe" fontSize={9} fontFamily="monospace">{a.id.slice(0, 10)}</text>
                <text textAnchor="middle" dy={30} fill="#94a3b8" fontSize={9}>{a.name}</text>
              </g>
            ))}
          </svg>
          <p className="mt-1 flex items-center gap-2 text-[11px] text-slate-500"><MousePointer2 size={11} /> Drag nodes to arrange · <Waypoints size={11} /> click one node, then another, to connect</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-slate-700 bg-slate-900 px-2 py-2 text-sm" aria-label="Twin name" />
            <button onClick={() => void save()} className="flex items-center gap-1 rounded bg-cyan-600 px-3 py-2 text-xs font-bold"><Save size={13} /> Save Twin</button>
            <button onClick={() => void api.activateBuiltinTwin().then((r) => set({ twin: r.twin, designerTwinId: null }))} className="rounded border border-slate-600 px-3 py-2 text-xs">Restore Built-in Twin</button>
          </div>
        </section>

        <section className="lg:col-span-3 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <h2 className="text-xs font-bold tracking-wider text-cyan-300">SAVED TWINS</h2>
          {customTwins.length === 0 && <p className="mt-2 text-xs text-slate-500">None yet — design and save one.</p>}
          {customTwins.map((t) => (
            <div key={t.id} className="mt-2 rounded bg-slate-950/60 p-2 text-xs">
              <b>{t.name}</b><div className="text-slate-500">{t.assets.length} assets · {t.connections.length} connections</div>
              <div className="mt-1 flex gap-1">
                <button onClick={() => void activate(t.id)} className="flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 font-bold text-slate-950"><Play size={11} /> Activate</button>
                <button onClick={() => { setAssets(t.assets.map((a) => ({ ...a, posture: a.posture ?? 0.7, vulnerabilities: a.vulnerabilities ?? [], pos: [a.pos[0], a.pos[1], a.pos[2]] as [number, number, number] }))); setConns(t.connections.map((c) => ({ source: c.source, target: c.target, trust: c.trust ?? 'medium', traversable: c.traversable ?? true, types: c.types ?? ['network'] }))); setName(t.name) }} className="rounded border border-slate-600 px-2 py-1">Load to Edit</button>
                <button onClick={() => void api.deleteCustomTwin(t.id).then(refresh)} className="rounded border border-red-800 px-2 py-1 text-red-300">Delete</button>
              </div>
            </div>
          ))}
        </section>
      </div>
    </main>
  )
}
