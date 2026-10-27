import type { Twin } from '../types'

/** SVG front panel generated from twin device link states. */
export default function Faceplate({ twin, assetId, onPort }: {
  twin: Twin
  assetId: string
  onPort?: (port: string) => void
}) {
  const dev = twin.devices?.find((d) => d.asset_id === assetId)
  const asset = twin.assets.find((a) => a.id === assetId)
  if (!dev || !asset) return <p className="text-xs text-slate-500">Device not in twin.</p>
  const ports = dev.ports.length ? dev.ports : ['eth0']
  return (
    <div className="rounded-lg border border-slate-700 bg-gradient-to-b from-slate-800 to-slate-950 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[11px] text-slate-300">{dev.vendor} · {dev.model}</span>
        <span className={`font-mono text-[10px] ${asset.status === 'healthy' ? 'text-emerald-300' : 'text-amber-300'}`}>{asset.status.toUpperCase()}</span>
      </div>
      <svg viewBox={`0 0 ${Math.max(ports.length * 44 + 20, 220)} 64`} className="w-full" role="img" aria-label={`Faceplate of ${asset.name}`}>
        <rect x={1} y={1} width={Math.max(ports.length * 44 + 18, 218)} height={62} rx={8} fill="#0b1220" stroke="#334155" />
        {ports.map((p, i) => {
          const link = dev.links[i % Math.max(dev.links.length, 1)]
          const color = !link ? '#475569' : link.state === 'up' ? '#22c55e' : link.state === 'filtered' ? '#f59e0b' : '#ef4444'
          return (
            <g key={p} transform={`translate(${14 + i * 44},14)`} onClick={() => onPort?.(p)} style={{ cursor: onPort ? 'pointer' : 'default' }}>
              <rect width={32} height={26} rx={4} fill="#111c2e" stroke="#475569" />
              <circle cx={16} cy={-5} r={3.5} fill={color}>
                {link?.state === 'up' && <animate attributeName="opacity" values="1;0.35;1" dur="1.6s" repeatCount="indefinite" />}
              </circle>
              <text x={16} y={48} textAnchor="middle" fill="#94a3b8" fontSize={7.5} fontFamily="monospace">{p}</text>
            </g>
          )
        })}
      </svg>
      <p className="mt-1 font-mono text-[9px] text-slate-500">LEDs: green up · amber filtered · red down/isolated · Emulated for simulation. Not affiliated with any vendor.</p>
    </div>
  )
}
