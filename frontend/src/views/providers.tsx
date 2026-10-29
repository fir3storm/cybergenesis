import { useEffect, useState } from 'react'
import { CheckCircle2, KeyRound, Plug } from 'lucide-react'
import { api } from '../services/api'
import type { ProviderInfo } from '../types'

/** Settings: choose the AI provider (Meta / Command Code / Kilo / Google AI Studio).
 * Keys are sent to the backend once and stored on this machine only; they are never shown back. */
export function ProviderSettings({ onChanged }: { onChanged: () => void }) {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [drafts, setDrafts] = useState<Record<string, { key: string; model: string; base: string }>>({})
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [operatorToken, setOperatorToken] = useState('')

  const saveOperatorToken = () => {
    try {
      if (operatorToken.trim()) sessionStorage.setItem('cybergenesis_admin_token', operatorToken.trim())
      else sessionStorage.removeItem('cybergenesis_admin_token')
      setOperatorToken('')
      setMsg('Operator access updated for this browser session.')
    } catch { setMsg('Browser session storage is unavailable; operator access could not be saved.') }
  }

  const load = () => api.providers().then((r) => {
    if (r.admin_token) {
      try { sessionStorage.setItem('cybergenesis_admin_token', r.admin_token) } catch {}
    }
    setProviders(r.providers)
    setDrafts(Object.fromEntries(r.providers.map((p) => [p.id, { key: '', model: p.model, base: p.base_url }])))
  }).catch((e: Error) => setMsg(`Could not load providers: ${e.message}`))
  useEffect(() => { void load() }, [])

  const activate = (p: ProviderInfo) => {
    const d = drafts[p.id] ?? { key: '', model: p.model, base: p.base_url }
    setBusy(p.id); setMsg(null)
    api.activateProvider(p.id, d.key, d.model, d.base)
      .then((r) => {
        setMsg(r.configured
          ? `${p.label} is now active (model ${r.model || '—'}). ${r.reachable ? 'Provider reachable.' : 'Saved; reachability: ' + r.detail}`
          : `${p.label} selected, but not configured yet: ${r.detail}`)
        void load(); onChanged()
      })
      .catch((e: Error) => setMsg(`Activation failed: ${e.message}`))
      .finally(() => setBusy(null))
  }

  return (
    <section aria-label="AI provider settings">
      <div className="mb-4 rounded-xl border border-slate-700 p-3">
        <label className="block text-sm text-slate-200">Operator token
          <input type="password" value={operatorToken} onChange={(e) => setOperatorToken(e.target.value)}
            autoComplete="off" placeholder="Token supplied by the instance owner"
            className="mt-2 block w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5" />
        </label>
        <p className="mt-1 text-xs text-slate-400">Shared instances require this token to run simulations, approve defenses, or change settings. It stays in this browser session.</p>
        <button onClick={saveOperatorToken} className="mt-2 rounded bg-cyan-700 px-3 py-1.5 text-xs text-white">Save operator access</button>
      </div>
      <h2 className="flex items-center gap-2 text-sm font-bold text-cyan-200"><Plug size={15} /> AI provider</h2>
      <p className="mt-1 text-xs text-slate-400">
        All providers speak the same OpenAI-compatible chat API, so every agent (Investigator, Strategist, Red Team, Arena)
        works with any of them. Paste a key, pick a model, activate — no restart needed. Keys are stored on this machine
        only and are never displayed or sent anywhere except that provider.
      </p>
      {msg && <p className="mt-2 rounded border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs text-slate-200" role="status">{msg}</p>}
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {providers.map((p) => {
          const d = drafts[p.id] ?? { key: '', model: p.model, base: p.base_url }
          const set = (patch: Partial<typeof d>) => setDrafts((prev) => ({ ...prev, [p.id]: { ...d, ...patch } }))
          return (
            <article key={p.id} className={`rounded-xl border p-4 ${p.active ? 'border-cyan-400 bg-cyan-950/30' : 'border-slate-800 glass-panel'}`}>
              <div className="flex items-center gap-2">
                <b className="text-slate-100">{p.label}</b>
                {p.active && <span className="flex items-center gap-1 rounded-full border border-cyan-500 px-2 py-0.5 text-[10px] font-bold text-cyan-200"><CheckCircle2 size={11} /> ACTIVE</span>}
                <span className={`ml-auto text-[10px] ${p.configured ? 'text-emerald-300' : 'text-slate-500'}`}>{p.configured ? 'key saved' : 'no key yet'}</span>
              </div>
              <p className="mt-1 text-xs text-slate-400">{p.description}</p>
              <label className="mt-2 block text-[11px] text-slate-400">Model
                <input value={d.model} onChange={(e) => set({ model: e.target.value })} placeholder={p.model_placeholder}
                  className="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-100" /></label>
              <label className="mt-2 block text-[11px] text-slate-400">API key <span className="text-slate-500">({p.key_hint})</span>
                <span className="relative mt-0.5 block">
                  <KeyRound size={12} className="absolute left-2 top-2 text-slate-500" />
                  <input type="password" value={d.key} onChange={(e) => set({ key: e.target.value })}
                    placeholder={p.configured ? 'saved — leave blank to keep it' : 'paste API key'}
                    className="w-full rounded border border-slate-700 bg-slate-900 py-1.5 pl-7 pr-2 text-xs text-slate-100" />
                </span></label>
              <label className="mt-2 block text-[11px] text-slate-400">Base URL
                <input value={d.base} onChange={(e) => set({ base: e.target.value })}
                  className="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-[11px] text-slate-100" /></label>
              <button onClick={() => activate(p)} disabled={busy === p.id}
                className="mt-3 rounded bg-cyan-600 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-40">
                {busy === p.id ? 'Activating…' : p.active ? 'Save & re-activate' : `Activate ${p.short}`}
              </button>
            </article>
          )
        })}
      </div>
      <p className="mt-2 text-[11px] text-slate-500">
        Prefer environment variables? Set the provider keys in <span className="font-mono">backend/.env</span> (see .env.example) and restart;
        Settings choices override them at runtime. OFFLINE_MODE still forces labelled deterministic mode for every provider.
      </p>
    </section>
  )
}
