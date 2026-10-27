import { useEffect, useState } from 'react'
import { Play, Plus, Save, Trash2 } from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { Library } from '../types'

interface Step { type: string; asset: string; description: string }
interface Defense { action_type: string; asset_id: string; params: Record<string, string> }

function TextToScenario() {
  const { set, customScenarios } = useStore()
  const [text, setText] = useState('what if the admin laptop is phished?')
  const [msg, setMsg] = useState<string | null>(null)
  const go = () => {
    setMsg('Muse Spark is writing the scenario…')
    api.fromText(text, 'AI What-If Scenario').then((sc) => {
      setMsg(`Created "${sc.name}" — validated against the asset/step/action allowlists. Run it from the list on the right.`)
      api.customScenarios().then((s) => set({ customScenarios: s })).catch(() => undefined)
      void customScenarios
    }).catch((e) => setMsg(`Failed honestly: ${(e as Error).message}`))
  }
  return (
    <div className="mb-4 rounded-xl border border-violet-800/60 bg-violet-950/30 p-3">
      <h2 className="text-xs font-bold tracking-wider text-violet-300">✨ TEXT-TO-SCENARIO (Meta AI)</h2>
      <div className="mt-2 flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} className="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-2 text-sm" aria-label="What-if prompt" />
        <button onClick={go} className="rounded bg-violet-600 px-3 py-2 text-xs font-bold">Generate + Validate</button>
      </div>
      {msg && <p className="mt-1 text-xs text-slate-300">{msg}</p>}
    </div>
  )
}

export default function AttackPlaybook({ onRunCustom }: { onRunCustom: (scenarioDbId: string, twinDbId: string | null) => void }) {
  const { twin, customTwins, customScenarios, set } = useStore()
  const [lib, setLib] = useState<Library | null>(null)
  const [name, setName] = useState('My Custom Attack')
  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [steps, setSteps] = useState<Step[]>([])
  const [defenses, setDefenses] = useState<Defense[]>([])
  const [runTwin, setRunTwin] = useState<string>('')
  const [msg, setMsg] = useState<string | null>(null)

  const assets = twin?.assets ?? []
  const refresh = () => {
    api.customScenarios().then((s) => set({ customScenarios: s })).catch(() => undefined)
    api.customTwins().then((t) => set({ customTwins: t })).catch(() => undefined)
  }
  useEffect(() => { api.library().then(setLib).catch(() => undefined); refresh() }, []) // eslint-disable-line
  useEffect(() => { if (!source && assets[0]) setSource(assets[0].id); if (!target && assets[1]) setTarget(assets[1].id) }, [assets]) // eslint-disable-line

  function addStep(typeId: string) {
    const item = lib?.attack_steps.find((s) => s.id === typeId)
    setSteps([...steps, { type: typeId, asset: source || assets[0]?.id || '', description: `${item?.description ?? typeId} (synthetic, on ${source || 'asset'})` }])
  }
  function addDefense(actionId: string) {
    const needsConn = actionId === 'block_connection'
    setDefenses([...defenses, {
      action_type: actionId, asset_id: needsConn ? source : source,
      params: needsConn ? { source, target } : actionId.includes('session') || actionId.includes('credential') ? { identity: 'admin-01' } : {},
    }])
  }

  async function save() {
    try {
      const saved = await api.createCustomScenario({
        name, description: 'Authored in Attack Playbook', source_asset: source, target_asset: target,
        severity: 'high', verification_kind: 'reachability',
        invariant: `${source} cannot reach ${target} after defense`,
        objectives: ['custom_objective'], attack_steps: steps, expected_defense: defenses,
      })
      setMsg(`Saved scenario "${saved.name}". Run it below — policy validation and verification are identical to builtin scenarios.`)
      refresh()
    } catch (e) { setMsg(`Save failed: ${(e as Error).message} — steps must use library step types and ≥1 step is required.`) }
  }

  const sel = 'rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs'
  return (
    <main className="p-6">
      <h1 className="text-2xl font-black text-cyan-200">Attack Playbook Creator</h1>
      <p className="mt-1 text-sm text-slate-400">Compose a synthetic attack from the step library, choose the expected defense, save, and run it through the same Observe → Reason → Policy → Act → Verify loop. Step types are allowlisted — arbitrary payloads are rejected by the API.</p>
      {msg && <div className="mt-3 rounded border border-cyan-800 bg-slate-900 px-3 py-2 text-sm text-cyan-200">{msg}</div>}
      <div className="mt-4"><TextToScenario /></div>
      <div className="mt-4 grid gap-4 lg:grid-cols-12">
        <section className="lg:col-span-4 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <h2 className="text-xs font-bold tracking-wider text-cyan-300">1 · STEP LIBRARY</h2>
          <div className="mt-2 space-y-1">
            {lib?.attack_steps.map((s) => (
              <button key={s.id} onClick={() => addStep(s.id)} className="block w-full rounded bg-slate-800/70 px-2 py-1.5 text-left text-xs hover:bg-slate-700">
                <Plus size={11} className="inline" /> <b>{s.label}</b> — <span className="text-slate-400">{s.description}</span>
                {s.mitre && <span className="block font-mono text-[9px] text-amber-300/80">MITRE {s.mitre} · {s.d3fend}</span>}
              </button>
            ))}
          </div>
          <h2 className="mt-4 text-xs font-bold tracking-wider text-cyan-300">2 · DEFENSE LIBRARY (expected)</h2>
          <div className="mt-2 space-y-1">
            {lib?.defense_actions.map((d) => (
              <button key={d.id} onClick={() => addDefense(d.id)} className="block w-full rounded bg-slate-800/70 px-2 py-1.5 text-left text-xs hover:bg-slate-700">
                <Plus size={11} className="inline" /> <b>{d.label}</b> <span className="text-slate-500">{d.params_contract}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="lg:col-span-4 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <h2 className="text-xs font-bold tracking-wider text-cyan-300">3 · COMPOSE</h2>
          <label className="mt-2 block text-xs text-slate-400">Name<input value={name} onChange={(e) => setName(e.target.value)} className={`${sel} mt-1 w-full`} /></label>
          <div className="mt-2 flex gap-2">
            <label className="text-xs text-slate-400">Source<select value={source} onChange={(e) => setSource(e.target.value)} className={sel}>{assets.map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}</select></label>
            <label className="text-xs text-slate-400">Target<select value={target} onChange={(e) => setTarget(e.target.value)} className={sel}>{assets.map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}</select></label>
          </div>
          <h3 className="mt-3 text-xs font-bold text-slate-300">Attack steps ({steps.length})</h3>
          {steps.map((s, i) => (
            <div key={i} className="mt-1 flex items-center gap-1 text-xs">
              <select value={s.asset} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, asset: e.target.value } : x))} className={sel}>
                {assets.map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}
              </select>
              <span className="flex-1 rounded bg-slate-950/60 px-2 py-1.5">{s.type}</span>
              <button aria-label="delete step" onClick={() => setSteps(steps.filter((_, j) => j !== i))}><Trash2 size={12} className="text-red-300" /></button>
            </div>
          ))}
          <h3 className="mt-3 text-xs font-bold text-slate-300">Expected defenses ({defenses.length})</h3>
          {defenses.map((d, i) => (
            <div key={i} className="mt-1 flex items-center gap-1 text-xs">
              <span className="flex-1 rounded bg-slate-950/60 px-2 py-1.5">{d.action_type} on {d.asset_id} {Object.keys(d.params).length ? JSON.stringify(d.params) : ''}</span>
              <button aria-label="delete defense" onClick={() => setDefenses(defenses.filter((_, j) => j !== i))}><Trash2 size={12} className="text-red-300" /></button>
            </div>
          ))}
          <button onClick={() => void save()} className="mt-3 flex items-center gap-1 rounded bg-cyan-600 px-3 py-2 text-xs font-bold"><Save size={13} /> Save Scenario</button>
        </section>

        <section className="lg:col-span-4 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <h2 className="text-xs font-bold tracking-wider text-cyan-300">4 · RUN</h2>
          <label className="mt-2 block text-xs text-slate-400">Run against twin
            <select value={runTwin} onChange={(e) => setRunTwin(e.target.value)} className={`${sel} mt-1 w-full`}>
              <option value="">Active twin ({assets.length} assets)</option>
              {customTwins.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select></label>
          {customScenarios.length === 0 && <p className="mt-2 text-xs text-slate-500">No custom scenarios yet — compose and save one.</p>}
          {customScenarios.map((sc) => (
            <div key={sc.id} className="mt-2 rounded bg-slate-950/60 p-2 text-xs">
              <b>{sc.name}</b>
              <div className="text-slate-500">{String(sc.definition.source_asset)} → {String(sc.definition.target_asset)} · {(sc.definition.attack_steps as unknown[])?.length ?? 0} steps</div>
              <div className="mt-1 flex gap-1">
                <button onClick={() => onRunCustom(sc.id, runTwin || null)} className="flex items-center gap-1 rounded bg-emerald-500 px-2 py-1 font-bold text-slate-950"><Play size={11} /> Run Experiment</button>
                <button onClick={() => void api.deleteCustomScenario(sc.id).then(refresh)} className="rounded border border-red-800 px-2 py-1 text-red-300">Delete</button>
              </div>
            </div>
          ))}
          <p className="mt-3 text-[11px] text-slate-500">Note: source/target and step assets must exist in the chosen twin, or the run fails honestly with that validation error.</p>
        </section>
      </div>
    </main>
  )
}
