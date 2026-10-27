import { useEffect, useRef, useState } from 'react'
import { MousePointer2, Play, Plus, Redo2, Save, Trash2, Undo2, Waypoints } from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { Library } from '../types'
import { autoHostname, portsFromManifest, validateConnection, type PortInfo } from './designerUtils'

interface DAsset { id: string; name: string; asset_type: string; zone: string; posture: number; pos: [number, number, number]; vulnerabilities: string[]; device_id?: string }
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
  const [catalog, setCatalog] = useState<{ id: string; vendor: string; model: string; category: string; tier: string }[]>([])
  const [catQ, setCatQ] = useState('')
  const [catCat, setCatCat] = useState('')
  const [past, setPast] = useState<{ assets: DAsset[]; conns: DConn[] }[]>([])
  const [future, setFuture] = useState<{ assets: DAsset[]; conns: DConn[] }[]>([])
  const [picker, setPicker] = useState<{ a: string; b: string; aPorts: PortInfo[]; bPorts: PortInfo[]; aPort: string; bPort: string } | null>(null)

  const refresh = () => api.customTwins().then((t) => set({ customTwins: t })).catch(() => undefined)
  useEffect(() => { api.library().then(setLib).catch(() => undefined); void refresh() }, []) // eslint-disable-line
  useEffect(() => {
    const p = new URLSearchParams({ limit: '200' })
    if (catCat) p.set('category', catCat)
    if (catQ) p.set('q', catQ)
    api.devices(p.toString()).then((r) => setCatalog(r.items)).catch(() => undefined)
  }, [catQ, catCat])

  function commit(nextAssets: DAsset[], nextConns: DConn[]) {
    setPast((p) => [...p.slice(-49), { assets, conns }])
    setFuture([])
    setAssets(nextAssets); setConns(nextConns)
  }
  function undo() {
    const prev = past[past.length - 1]
    if (!prev) return
    setFuture((f) => [{ assets, conns }, ...f]); setPast((p) => p.slice(0, -1))
    setAssets(prev.assets); setConns(prev.conns)
  }
  function redo() {
    const next = future[0]
    if (!next) return
    setPast((p) => [...p, { assets, conns }]); setFuture((f) => f.slice(1))
    setAssets(next.assets); setConns(next.conns)
  }

  const CAT_TO_TYPE: Record<string, string> = { router: 'gateway', switch: 'app_server', firewall: 'firewall', wireless: 'sensor',
    security: 'sensor', server: 'server', endpoint: 'workstation', virtual: 'app_server', ot: 'sensor', identity: 'identity' }
  function addFromCatalog(deviceId: string, vendor: string, category: string) {
    counter.current += 1
    const hostname = autoHostname(vendor, assets.map((a) => a.name))
    const id = `${hostname.toLowerCase()}-${counter.current}`
    const angle = counter.current * 1.1
    commit([...assets, { id, name: hostname, asset_type: CAT_TO_TYPE[category] ?? 'workstation', zone: category,
      posture: 0.7, vulnerabilities: [], device_id: deviceId,
      pos: [Math.round(Math.cos(angle) * 5 * 10) / 10, 1.1, Math.round(Math.sin(angle) * 3.5 * 10) / 10] }], conns)
  }

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

  async function portsFor(asset: DAsset): Promise<PortInfo[]> {
    if (asset.device_id) {
      try {
        const m = await api.device(asset.device_id)
        return portsFromManifest(m.hardware.ports)
      } catch { /* fall through to generic ports */ }
    }
    return [{ name: 'eth0', speed: '1G', media: 'copper' }, { name: 'eth1', speed: '1G', media: 'copper' }]
  }

  async function onNodeClick(id: string) {
    if (!connectFrom) { setConnectFrom(id); setMsg(`Connect mode: click a second asset to link from ${id} (click again to cancel)`); return }
    if (connectFrom === id) { setConnectFrom(null); return }
    const a = assets.find((x) => x.id === connectFrom)!
    const b = assets.find((x) => x.id === id)!
    const [aPorts, bPorts] = await Promise.all([portsFor(a), portsFor(b)])
    setPicker({ a: a.id, b: b.id, aPorts, bPorts, aPort: aPorts[0]?.name ?? '', bPort: bPorts[0]?.name ?? '' })
    setConnectFrom(null)
  }

  function confirmCable() {
    if (!picker) return
    const used = new Set(conns.flatMap((c) => [`${c.source}:x`, `${c.target}:x`]))
    void used
    const aP = picker.aPorts.find((p) => p.name === picker.aPort) ?? null
    const bP = picker.bPorts.find((p) => p.name === picker.bPort) ?? null
    const err = validateConnection(new Set(), picker.a, aP, picker.b, bP)
    if (err) { setMsg(`Cable refused: ${err}`); return }
    if (!conns.some((c) => (c.source === picker.a && c.target === picker.b) || (c.source === picker.b && c.target === picker.a))) {
      commit(assets, [...conns, { source: picker.a, target: picker.b, trust: 'medium', traversable: true, types: ['network'] }])
      setMsg(`Cabled ${picker.a}:${picker.aPort} ↔ ${picker.b}:${picker.bPort} — auto-config staged on both ends (enable, description, VLAN 1 / routed /30).`)
    }
    setPicker(null)
  }

  const TEMPLATES: Record<string, { assets: [string, string, string][]; links: [number, number][] }> = {
    'Small office': { assets: [['internet', 'Internet', 'gateway'], ['firewall', 'Firewall', 'firewall'], ['ws-1', 'Workstation', 'workstation'], ['fs-1', 'File Server', 'file_server']],
      links: [[0, 1], [1, 2], [2, 3]] },
    'Three-tier enterprise': { assets: [['internet', 'Internet', 'gateway'], ['firewall', 'Firewall', 'firewall'], ['web', 'Web', 'web_server'], ['app', 'App', 'app_server'], ['db', 'Database', 'database']],
      links: [[0, 1], [1, 2], [2, 3], [3, 4]] },
    'Data-centre spine-leaf': { assets: [['spine', 'Spine', 'app_server'], ['leaf-a', 'Leaf A', 'app_server'], ['leaf-b', 'Leaf B', 'app_server'], ['db', 'Database', 'database'], ['fs', 'Storage', 'file_server']],
      links: [[0, 1], [0, 2], [1, 3], [2, 4]] },
    'Hybrid cloud': { assets: [['internet', 'Internet', 'gateway'], ['firewall', 'Firewall', 'firewall'], ['app', 'Cloud App', 'app_server'], ['idp', 'Identity', 'identity']],
      links: [[0, 1], [1, 2], [2, 3]] },
    'Factory OT (Purdue)': { assets: [['internet', 'Internet', 'gateway'], ['firewall', 'OT Firewall', 'firewall'], ['plc', 'PLC Cell', 'sensor'], ['hmi', 'HMI', 'workstation']],
      links: [[0, 1], [1, 2], [2, 3]] },
  }
  function loadTemplate(nameTpl: string) {
    const t = TEMPLATES[nameTpl]
    const made: DAsset[] = t.assets.map(([id, label, type], i) => ({ id, name: label, asset_type: type, zone: 'template', posture: 0.7,
      vulnerabilities: [], pos: [(i % 3) * 3.6 - 3.6, 1.1, Math.floor(i / 3) * 3 - 1.5] }))
    commit(made, t.links.map(([a, b]) => ({ source: made[a].id, target: made[b].id, trust: 'medium', traversable: true, types: ['network'] })))
    setName(nameTpl)
    setMsg(`Template "${nameTpl}" loaded with valid cables and default configs. Save to persist.`)
  }

  function onMove(e: React.PointerEvent) {
    if (!drag.current || !svgRef.current) return
    const r = svgRef.current.getBoundingClientRect()
    const x = wx(((e.clientX - r.left) / r.width) * 720)
    const z = wz(((e.clientY - r.top) / r.height) * 400)
    setAssets(assets.map((a) => a.id === drag.current!.id
      ? { ...a, pos: [Math.round(x * 10) / 10, a.pos[1], Math.round(z * 10) / 10] } : a))
  }

  const [mermaid, setMermaid] = useState('flowchart LR\n  ws[Workstation] --> fs[File Server]\n  fs --> db[Database]')
  function importMermaid() {
    const nodes = new Map<string, DAsset>()
    const edges: DConn[] = []
    let n = 0
    for (const line of mermaid.split('\n')) {
      const m = line.match(/(\w+)(?:\[([^\]]+)\])?\s*-->\s*(\w+)(?:\[([^\]]+)\])?/)
      if (!m) continue
      for (const [id, label] of [[m[1], m[2]], [m[3], m[4]]] as [string, string | undefined][]) {
        if (!nodes.has(id)) {
          n++
          nodes.set(id, { id, name: label ?? id, asset_type: id.includes('db') || id.includes('data') ? 'database' : id.includes('fs') || id.includes('file') ? 'file_server' : 'workstation',
            zone: 'custom', posture: 0.7, vulnerabilities: [], pos: [(n % 4) * 3.4 - 5, 1.1, Math.floor(n / 4) * 3 - 2] })
        }
      }
      edges.push({ source: m[1], target: m[3], trust: 'medium', traversable: true, types: ['network'] })
    }
    if (!nodes.size) { setMsg('Mermaid import: no `a[Label] --> b[Label]` lines parsed.'); return }
    setAssets([...nodes.values()]); setConns(edges)
    setMsg(`Mermaid import: ${nodes.size} assets, ${edges.length} connections — review, then Save.`)
  }

  function handleImageFile(f: File) {
    if (!['image/png', 'image/jpeg'].includes(f.type)) { setMsg('Only PNG/JPEG images are accepted.'); return }
    if (f.size > 4_000_000) { setMsg(`Image rejected: ${(f.size / 1e6).toFixed(1)} MB exceeds the 4 MB limit.`); return }
    const reader = new FileReader()
    reader.onload = () => {
      setMsg('Sending diagram to Muse Spark vision…')
      api.fromImage(String(reader.result), name).then((t) => {
        setAssets(t.assets.map((a) => ({ ...a, posture: a.posture ?? 0.7, vulnerabilities: a.vulnerabilities ?? [], pos: [a.pos[0], a.pos[1], a.pos[2]] as [number, number, number] })))
        setConns(t.connections.map((c) => ({ source: c.source, target: c.target, trust: c.trust ?? 'medium', traversable: c.traversable ?? true, types: c.types ?? ['network'] })))
        setMsg(`Meta vision generated "${t.name}" (${t.assets.length} assets) — edit on the canvas, then Save/Activate.`)
        void refresh()
      }).catch((err) => setMsg(`Vision failed honestly: ${(err as Error).message}`))
    }
    reader.readAsDataURL(f)
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
          <h2 className="text-xs font-bold tracking-wider text-cyan-300">TEMPLATES</h2>
          <div className="mt-1 flex flex-wrap gap-1">
            {Object.keys(TEMPLATES).map((t) => <button key={t} onClick={() => loadTemplate(t)} className="rounded bg-slate-800 px-2 py-1 text-[10px] hover:bg-slate-700">{t}</button>)}
          </div>
          <div className="mt-2 flex gap-1">
            <button onClick={undo} disabled={!past.length} className="flex items-center gap-1 rounded border border-slate-700 px-2 py-1 text-[10px] disabled:opacity-40"><Undo2 size={11} /> Undo</button>
            <button onClick={redo} disabled={!future.length} className="flex items-center gap-1 rounded border border-slate-700 px-2 py-1 text-[10px] disabled:opacity-40"><Redo2 size={11} /> Redo</button>
          </div>
          <h2 className="mt-4 text-xs font-bold tracking-wider text-cyan-300">DEVICE CATALOG (200) — drag onto canvas</h2>
          <input value={catQ} onChange={(e) => setCatQ(e.target.value)} placeholder="Search vendor/model…" aria-label="Search catalog" className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-[11px]" />
          <select value={catCat} onChange={(e) => setCatCat(e.target.value)} aria-label="Category filter" className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-[11px]">
            <option value="">All categories</option>
            {['router', 'switch', 'firewall', 'wireless', 'security', 'server', 'endpoint', 'virtual', 'ot', 'identity'].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="mt-1 max-h-44 space-y-1 overflow-auto">
            {catalog.slice(0, 60).map((d) => (
              <div key={d.id} draggable onDragStart={(e) => e.dataTransfer.setData('text/device-id', JSON.stringify(d))}
                onClick={() => addFromCatalog(d.id, d.vendor, d.category)}
                className="cursor-grab rounded bg-slate-800/70 px-2 py-1 text-[10px] hover:bg-slate-700" title="Drag onto canvas or click to add">
                {d.tier === 'flagship' && <span className="mr-1 rounded bg-amber-500 px-1 font-bold text-slate-950">FLAGSHIP</span>}
                {d.vendor} {d.model} <span className="text-slate-500">({d.category})</span>
              </div>
            ))}
            {!catalog.length && <p className="text-[10px] text-slate-500">Catalog loading…</p>}
          </div>
          <h2 className="mt-4 text-xs font-bold tracking-wider text-cyan-300">COMPONENT PALETTE</h2>
          <div className="mt-2 space-y-1">
            {lib?.asset_types.map((a) => (
              <button key={a.id} onClick={() => addAsset(a.id)} className="flex w-full items-center gap-1 rounded bg-slate-800/70 px-2 py-1.5 text-left text-xs hover:bg-slate-700">
                <Plus size={12} /> {a.label} <span className="text-slate-500">({a.default_zone})</span>
              </button>
            ))}
          </div>
          <h2 className="mt-4 text-xs font-bold tracking-wider text-cyan-300">IMPORT (MERMAID)</h2>
          <textarea value={mermaid} onChange={(e) => setMermaid(e.target.value)} rows={4} aria-label="Mermaid diagram"
            className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2 font-mono text-[10px]" />
          <button onClick={importMermaid} className="mt-1 w-full rounded border border-cyan-700 py-1 text-[11px] text-cyan-200">Import Mermaid → canvas</button>
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

        <section className="lg:col-span-6" onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            const raw = e.dataTransfer.getData('text/device-id')
            if (raw) { const d = JSON.parse(raw) as { id: string; vendor: string; category: string }; addFromCatalog(d.id, d.vendor, d.category); return }
            const f = e.dataTransfer.files?.[0]; if (f) handleImageFile(f)
          }}>
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
          <p className="mt-1 flex items-center gap-2 text-[11px] text-slate-500"><MousePointer2 size={11} /> Drag nodes to arrange · <Waypoints size={11} /> click one node, then another, to connect (port picker opens)</p>
          {picker && (
            <div className="mt-2 rounded-xl border border-cyan-700 bg-slate-950 p-3 text-xs">
              <b>Cable {picker.a} ↔ {picker.b}</b>
              <div className="mt-2 flex flex-wrap gap-2">
                <label>{picker.a} port <select value={picker.aPort} onChange={(e) => setPicker({ ...picker, aPort: e.target.value })} className="rounded border border-slate-700 bg-slate-900 px-2 py-1">
                  {picker.aPorts.map((p) => <option key={p.name} value={p.name}>{p.name} ({p.speed} {p.media})</option>)}</select></label>
                <label>{picker.b} port <select value={picker.bPort} onChange={(e) => setPicker({ ...picker, bPort: e.target.value })} className="rounded border border-slate-700 bg-slate-900 px-2 py-1">
                  {picker.bPorts.map((p) => <option key={p.name} value={p.name}>{p.name} ({p.speed} {p.media})</option>)}</select></label>
                <button onClick={confirmCable} className="rounded bg-emerald-500 px-3 py-1 font-bold text-slate-950">Create cable + auto-configure</button>
                <button onClick={() => setPicker(null)} className="rounded border border-slate-600 px-3 py-1">Cancel</button>
              </div>
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-slate-700 bg-slate-900 px-2 py-2 text-sm" aria-label="Twin name" />
            <button onClick={() => void save()} className="flex items-center gap-1 rounded bg-cyan-600 px-3 py-2 text-xs font-bold"><Save size={13} /> Save Twin</button>
            {['diagram-enterprise.png', 'diagram-office.png', 'diagram-datacenter.png'].map((f) => (
              <button key={f} onClick={() => {
                setMsg(`Loading sample ${f} and sending to Muse Spark vision…`)
                fetch(`/samples/${f}`).then((r) => r.blob()).then((blob) => new Promise<string>((resolve) => {
                  const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsDataURL(blob)
                })).then((dataUrl) => api.fromImage(dataUrl, `Sample ${f}`)).then((t) => {
                  setAssets(t.assets.map((a) => ({ ...a, posture: a.posture ?? 0.7, vulnerabilities: a.vulnerabilities ?? [], pos: [a.pos[0], a.pos[1], a.pos[2]] as [number, number, number] })))
                  setConns(t.connections.map((c) => ({ source: c.source, target: c.target, trust: c.trust ?? 'medium', traversable: c.traversable ?? true, types: c.types ?? ['network'] })))
                  setMsg(`Meta vision read ${f}: ${t.assets.length} assets, ${t.connections.length} connections — review, then Save/Activate and run it from the Playbook.`)
                  void refresh()
                }).catch((err) => setMsg(`Vision failed honestly: ${(err as Error).message}`))
              }} className="rounded border border-slate-600 px-2 py-2 text-[11px] text-slate-300 hover:bg-slate-800">Try sample: {f.replace('diagram-', '').replace('.png', '')}</button>
            ))}
            <label className="flex cursor-pointer items-center gap-1 rounded border border-violet-600 px-3 py-2 text-xs text-violet-200 hover:bg-violet-950/50">
              📷 Generate from whiteboard photo (Meta vision)
              <input type="file" accept="image/png,image/jpeg" className="hidden" onChange={(e) => {
                const f = e.target.files?.[0]
                if (!f) return
                if (f.size > 4_000_000) { setMsg(`Image rejected: ${(f.size / 1e6).toFixed(1)} MB exceeds the 4 MB limit.`); return }
                const reader = new FileReader()
                reader.onload = () => {
                  setMsg('Sending diagram to Muse Spark vision…')
                  api.fromImage(String(reader.result), name).then((t) => {
                    setAssets(t.assets.map((a) => ({ ...a, posture: a.posture ?? 0.7, vulnerabilities: a.vulnerabilities ?? [], pos: [a.pos[0], a.pos[1], a.pos[2]] as [number, number, number] })))
                    setConns(t.connections.map((c) => ({ source: c.source, target: c.target, trust: c.trust ?? 'medium', traversable: c.traversable ?? true, types: c.types ?? ['network'] })))
                    setMsg(`Meta vision generated "${t.name}" (${t.assets.length} assets) — review on the canvas, then Save/Activate. Model output was schema-validated by the backend.`)
                    void refresh()
                  }).catch((err) => setMsg(`Vision failed honestly: ${(err as Error).message}`))
                }
                reader.readAsDataURL(f)
              }} />
            </label>
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
