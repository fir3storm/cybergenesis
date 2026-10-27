import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Twin } from '../types'
import CliTerminal from './CliTerminal'
import { syntheticLoad } from './deviceLoad'

export { syntheticLoad } from './deviceLoad'

const TABS = ['Dashboard', 'Interfaces', 'VLANs', 'Routing', 'ACLs', 'Security Policies', 'NAT', 'VPN', 'Users/AAA', 'Management', 'Logs', 'CLI', 'Pending Changes'] as const

export default function DeviceManager({ assetId, twin, dialect }: { assetId: string; twin: Twin; dialect: string }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Dashboard')
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [pending, setPending] = useState<{ diff: unknown } | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const asset = twin.assets.find((a) => a.id === assetId)
  const isFw = asset?.asset_type === 'firewall'

  const load = () => api.deviceConfig(assetId).then((r) => setConfig(r.config)).catch(() => undefined)
  useEffect(() => { load() }, [assetId]) // eslint-disable-line
  useEffect(() => { api.deviceConfig(assetId).catch(() => undefined); fetchPending() }, [assetId]) // eslint-disable-line
  const fetchPending = () => fetch(`${''}`).catch(() => undefined)

  const stageAction = (action_type: string, params: Record<string, unknown> = {}) => {
    const diff = { ops: [{ op: 'action', value: { action_type, asset_id: assetId, params } }] }
    api.stageDiff(assetId, diff).then(() => { setPending({ diff }); setTab('Pending Changes'); setMsg('Diff staged. Preview impact, then commit.') }).catch((e) => setMsg(String((e as Error).message)))
  }
  const doPreview = () => {
    if (!pending) return
    api.previewDiff(assetId, pending.diff).then((r) => setPreview(r.changes.length
      ? r.changes.map((c) => `${c.src}→${c.dst}: ${c.before_reachable} → ${c.after_reachable}`).join(' · ')
      : 'No scenario path changes.')).catch((e) => setPreview(String((e as Error).message)))
  }
  const doCommit = () => {
    api.commitDiff(assetId).then((r) => { setMsg('Committed — twin updated (twin_updated broadcast).'); setPending(null); load(); if (r.twin) useTwinRefresh(r.twin) })
      .catch(async (e) => {
        setMsg(`Commit rejected: ${(e as Error).message} — check Pending Changes for the policy reason (403 detail is in the API response).`)
      })
  }
  const useTwinRefresh = (t: Twin) => { void t }

  return (
    <div>
      <div className="flex flex-wrap gap-1">
        {TABS.filter((t) => isFw || t !== 'Security Policies').map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`rounded px-2 py-1 text-[11px] ${tab === t ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-300'}`}>{t}</button>
        ))}
      </div>
      {msg && <p className="mt-2 text-xs text-cyan-300">{msg}</p>}
      <div className="mt-3 text-xs">
        {tab === 'Dashboard' && (() => {
          const load = syntheticLoad(asset?.status, assetId)
          return (
            <div>
              <div className="grid grid-cols-3 gap-2">
                {[['Status', asset?.status], ['Zone', asset?.zone], ['Posture', `${Math.round((asset?.posture ?? 0) * 100)}%`],
                  ['CPU (synthetic)', `${load.cpu}%`], ['Memory (synthetic)', `${load.memory}%`], ['Sessions', String(asset?.connected.length ?? 0)]].map(([k, v]) => (
                  <div key={k} className="rounded bg-slate-900 p-2"><div className="text-slate-300">{k}</div><b>{v}</b></div>
                ))}
              </div>
              <p className="mt-1 font-mono text-[9px] text-slate-300">CPU/memory are synthetic values derived deterministically from twin status ({asset?.status ?? 'unknown'}), not real telemetry.</p>
            </div>
          )
        })()}
        {tab === 'Interfaces' && (
          <table className="w-full text-left"><thead><tr className="text-slate-500"><th>Name</th><th>Peer</th><th>IP</th><th>Zone</th><th>Action</th></tr></thead>
            <tbody>{((config?.interfaces ?? []) as { name: string; peer?: string; ip?: string; zone?: string }[]).map((i) => (
              <tr key={i.name} className="border-t border-slate-800"><td className="py-1 font-mono">{i.name}</td><td>{i.peer}</td><td>{i.ip}</td><td>{i.zone}</td>
                <td><button onClick={() => stageAction('isolate_asset')} className="text-red-300">isolate device</button></td></tr>))}
            </tbody></table>
        )}
        {tab === 'ACLs' && (
          <div>
            <p className="text-slate-400">Stage a deny-all ACL (ConfigDiff) on this device:</p>
            <button onClick={() => stageAction('block_connection', { source: assetId, target: asset?.connected[0] ?? '', direction: 'egress' })} disabled={!asset?.connected.length}
              className="mt-2 rounded bg-amber-600 px-3 py-1.5 font-bold disabled:opacity-40">Stage egress deny to {asset?.connected[0] ?? '—'}</button>
          </div>
        )}
        {tab === 'Security Policies' && (
          <table className="w-full text-left"><thead><tr className="text-slate-500"><th>#</th><th>From</th><th>To</th><th>Service</th><th>Action</th></tr></thead>
            <tbody><tr className="border-t border-slate-800"><td>1</td><td>any</td><td>any</td><td>any</td><td className="text-red-300">deny (implicit)</td></tr></tbody></table>
        )}
        {tab === 'Users/AAA' && (
          <div className="space-y-1">
            {((config?.users ?? []) as { name: string; role: string; mfa: boolean }[]).map((u) => (
              <div key={u.name} className="flex justify-between rounded bg-slate-900 px-2 py-1"><span>{u.name} ({u.role}) · MFA {u.mfa ? 'on' : 'OFF'}</span>
                {!u.mfa && <button onClick={() => stageAction('enforce_mfa', { identity: u.name })} className="text-cyan-300">enforce MFA</button>}</div>
            ))}
            {!((config?.users ?? []) as unknown[]).length && <p className="text-slate-500">No local users on this device.</p>}
          </div>
        )}
        {tab === 'Management' && (
          <div>
            <pre className="rounded bg-slate-950 p-2 font-mono text-[10px]">{JSON.stringify(config?.mgmt ?? {}, null, 1)}</pre>
            <button onClick={() => stageAction('harden_mgmt')} className="mt-2 rounded bg-cyan-600 px-3 py-1.5 font-bold">Stage harden_mgmt (telnet off, SSH on)</button>
            <button onClick={() => {
              api.stageDiff(assetId, { ops: [{ op: 'set', path: 'isolated', value: true }] })
                .then(() => { setPending({ diff: { ops: [{ op: 'set', path: 'isolated', value: true }] } }); setTab('Pending Changes'); setMsg('Staged set isolated=true — commit will run the policy gate.') })
                .catch((e) => setMsg(String((e as Error).message)))
            }} className="ml-2 mt-2 rounded border border-red-700 px-3 py-1.5 text-red-300">Stage set isolated=true (policy-gated)</button>
          </div>
        )}
        {tab === 'Logs' && <pre className="rounded bg-slate-950 p-2 font-mono text-[10px] text-emerald-200/80">{`${new Date().toISOString()} ${assetId} %LINK-5-CHANGED: status ${asset?.status}\n${new Date().toISOString()} ${assetId} %SEC-6-IPACCESSLOGP: synthetic telemetry only`}</pre>}
        {tab === 'CLI' && <CliTerminal assetId={assetId} dialect={dialect} />}
        {tab === 'Pending Changes' && (
          <div>
            {!pending && <p className="text-slate-500">No staged diff. Make an edit in Interfaces / ACLs / Users / Management.</p>}
            {pending && <pre className="rounded bg-slate-950 p-2 font-mono text-[10px]">{JSON.stringify(pending.diff, null, 1)}</pre>}
            {preview && <p className="mt-1 text-amber-200">Preview impact: {preview}</p>}
            <div className="mt-2 flex gap-2">
              <button onClick={doPreview} disabled={!pending} className="rounded border border-cyan-700 px-3 py-1.5 disabled:opacity-40">Preview impact</button>
              <button onClick={doCommit} disabled={!pending} className="rounded bg-emerald-500 px-3 py-1.5 font-bold text-slate-950 disabled:opacity-40">Commit (verified)</button>
            </div>
          </div>
        )}
        {!['Dashboard', 'Interfaces', 'ACLs', 'Security Policies', 'Users/AAA', 'Management', 'Logs', 'CLI', 'Pending Changes'].includes(tab) && (
          <pre className="rounded bg-slate-950 p-2 font-mono text-[10px]">{JSON.stringify(config?.[tab.toLowerCase()] ?? [], null, 1)}</pre>
        )}
      </div>
    </div>
  )
}
