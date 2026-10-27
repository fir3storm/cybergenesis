import { useEffect, useState } from 'react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { Asset, RunResult, Twin, View } from '../types'
import { Component, Suspense, lazy, type ReactNode } from 'react'
import { ATTACK_PATHS, STATUS_COLOR } from '../components/status'
import { Shield } from 'lucide-react'
import { useOpenDevice } from '../components/DeviceWindow'

const TwinScene = lazy(() => import('../components/TwinScene'))

class SceneBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

export function SkeletonTwin() {
  return (
    <div className="grid h-full grid-cols-3 gap-3 p-4" aria-label="Loading 3D twin" role="status">
      {Array.from({ length: 9 }, (_, i) => <div key={i} className="skeleton min-h-16" />)}
    </div>
  )
}

export function TwinView({ twin }: { twin: Twin }) {
  return (
    <SceneBoundary fallback={<div><p className="p-3 text-amber-300 text-sm">3D unavailable (WebGL) — 2D fallback shown. All functions remain available.</p><Twin2D twin={twin} /></div>}>
      <Suspense fallback={<SkeletonTwin />}>
        <TwinScene twin={twin} />
      </Suspense>
    </SceneBoundary>
  )
}

export function Twin2D({ twin }: { twin: Twin }) {
  const { selectedAsset, set } = useStore()
  const openDevice = useOpenDevice()
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-2 p-3" role="list" aria-label="Infrastructure assets (2D view)">
      {twin.assets.map((a) => (
        <button key={a.id} role="listitem" onClick={() => set({ selectedAsset: a.id })}
          onDoubleClick={() => openDevice(a.id, twin, a.name)} title="Double-click to open device window"
          className={`text-left rounded-lg border p-3 bg-slate-900/70 ${selectedAsset === a.id ? 'border-cyan-300' : 'border-slate-700'}`}>
          <div className="text-xs font-mono" style={{ color: STATUS_COLOR[a.status] }}>{a.status.toUpperCase()}</div>
          <div className="text-sm font-semibold">{a.name}</div>
          <div className="text-[11px] text-slate-400">{a.zone} · posture {(a.posture * 100).toFixed(0)}%</div>
        </button>
      ))}
    </div>
  )
}

export function AttackChain() {
  const s = useStore()
  const path = ATTACK_PATHS[s.scenarioId] ?? []
  const byId = Object.fromEntries((s.twin?.assets ?? []).map((a) => [a.id, a]))
  const blocked = s.results?.verification?.metrics.after_reachable_or_granted === false
  if (!path.length) return null
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded-xl border border-red-900/50 glass-panel px-3 py-2" aria-label="Attack path in plain language">
      <span className="font-mono text-[10px] tracking-wider text-red-300">ATTACK PATH</span>
      {path.map((id, i) => {
        const a = byId[id]
        const role = i === 0 ? 'SOURCE' : i === path.length - 1 ? 'TARGET' : `PIVOT ${i}`
        return (
          <span key={id} className="flex items-center gap-1.5">
            {i > 0 && <span className={blocked && i === path.length - 1 ? 'text-emerald-300 font-bold' : 'text-red-400'}>{blocked && i === path.length - 1 ? '✕ blocked →' : '→'}</span>}
            <button onClick={() => s.set({ selectedAsset: id })} className="rounded-full border px-2 py-1 text-[11px]"
              style={{ borderColor: STATUS_COLOR[a?.status ?? 'healthy'], color: STATUS_COLOR[a?.status ?? 'healthy'] }}>
              <b>{i + 1}</b> {a?.name ?? id} <span className="opacity-70">· {role} · {(a?.status ?? '—').toUpperCase()}</span>
            </button>
          </span>
        )
      })}
      <span className={`ml-auto text-[11px] ${blocked ? 'text-emerald-300 font-bold' : 'text-slate-400'}`}>
        {s.results?.verification ? (blocked ? '✓ Defense cut this path (verified)' : '✗ Path still open (verification failed)') : 'Run an experiment to test this path'}
      </span>
    </div>
  )
}

export function MapFocusToggle() {
  const s = useStore()
  return (
    <div className="flex items-center gap-1 text-[11px]">
      <span className="text-slate-500">Map:</span>
      <button onClick={() => s.set({ mapFocus: true })} className={`rounded-full border px-2 py-0.5 ${s.mapFocus ? 'border-red-400 bg-red-500/20 text-red-200' : 'border-slate-700 text-slate-400'}`}>Attack path only</button>
      <button onClick={() => s.set({ mapFocus: false })} className={`rounded-full border px-2 py-0.5 ${!s.mapFocus ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200' : 'border-slate-700 text-slate-400'}`}>Full topology</button>
    </div>
  )
}

export function AssetPanel({ asset }: { asset: Asset }) {
  const twin = useStore((s) => s.twin)
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2"><Shield size={16} className="text-cyan-300" /><b>{asset.name}</b></div>
      <div>Status: <span style={{ color: STATUS_COLOR[asset.status] }}>{asset.status}</span></div>
      <div>Zone: {asset.zone} · Type: {asset.asset_type}</div>
      <div>Security posture: {(asset.posture * 100).toFixed(0)}%</div>
      <div>Isolated: {asset.isolated ? 'yes (contained)' : 'no'} · Service disabled: {asset.service_disabled ? 'yes' : 'no'}</div>
      <div>Simulated vulnerabilities: {asset.vulnerabilities.length ? asset.vulnerabilities.join(', ') : 'none'}</div>
      <div>Connected: {asset.connected.join(', ') || 'none'}</div>
      {twin && <div>Containment: {twin.containment.join(', ') || 'none active'}</div>}
    </div>
  )
}
