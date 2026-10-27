import type { Twin } from '../types'
import { faceplateGrid, ledColor, linkStateForPort } from './faceplateUtils'

/**
 * SVG front panel generated from twin device data.
 *
 * Ports come from `twin.devices[].ports` (backend: catalog manifest, no
 * truncation) and are all shown — large counts wrap into a compact
 * multi-row grid rather than being dropped. LED states reflect the live
 * link state in `twin.devices[].links` (up/filtered/down from the twin,
 * forced down when the asset is isolated).
 */
export default function Faceplate({ twin, assetId, onPort }: {
  twin: Twin
  assetId: string
  onPort?: (port: string) => void
}) {
  const dev = twin.devices?.find((d) => d.asset_id === assetId)
  const asset = twin.assets.find((a) => a.id === assetId)
  if (!dev || !asset) return <p className="text-xs text-slate-300">Device not in twin.</p>
  const ports = dev.ports.length ? dev.ports : ['eth0']
  const grid = faceplateGrid(ports.length)
  const upCount = dev.links.filter((l) => l.state === 'up' && !asset.isolated).length
  return (
    <div className="rounded-lg border border-slate-700 bg-gradient-to-b from-slate-800 to-slate-950 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[11px] text-slate-300">{dev.vendor} · {dev.model}</span>
        <span className="font-mono text-[10px] text-slate-300">{ports.length} ports · {upCount}/{dev.links.length} links up</span>
        <span className={`font-mono text-[10px] ${asset.status === 'healthy' ? 'text-emerald-300' : 'text-amber-300'}`}>{asset.status.toUpperCase()}</span>
      </div>
      <svg viewBox={`0 0 ${grid.width} ${grid.height}`} className="w-full" role="img" aria-label={`Faceplate of ${asset.name} with ${ports.length} ports`}>
        <rect x={1} y={1} width={grid.width - 2} height={grid.height - 2} rx={8} fill="#0b1220" stroke="#334155" />
        {ports.map((p, i) => {
          const state = linkStateForPort(dev.links, i, asset.isolated)
          const color = ledColor(state, asset.isolated)
          const col = i % grid.perRow
          const row = Math.floor(i / grid.perRow)
          const cx = grid.boxW / 2
          return (
            <g key={p} transform={`translate(${14 + col * grid.step},${14 + row * grid.rowH})`} onClick={() => onPort?.(p)} style={{ cursor: onPort ? 'pointer' : 'default' }}>
              <title>{`${p}${state ? ` — link ${state}` : ' — no link'}`}</title>
              <rect width={grid.boxW} height={grid.boxH} rx={4} fill="#111c2e" stroke="#475569" />
              <circle cx={cx} cy={-5} r={3.5} fill={color}>
                {state === 'up' && !asset.isolated && <animate attributeName="opacity" values="1;0.35;1" dur="1.6s" repeatCount="indefinite" />}
              </circle>
              <text x={cx} y={48} textAnchor="middle" fill="#cbd5e1" fontSize={grid.step > 36 ? 7.5 : 6.5} fontFamily="monospace">{p}</text>
            </g>
          )
        })}
      </svg>
      <p className="mt-1 font-mono text-[9px] text-slate-300">LEDs: green up · amber filtered · red down/isolated · grey no link · all {ports.length} ports shown · Emulated for simulation. Not affiliated with any vendor.</p>
    </div>
  )
}
