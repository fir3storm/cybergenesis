import { Suspense, lazy, useEffect, useState } from 'react'
import { api } from '../services/api'
import { useWindows } from './WindowManager'
import Faceplate from './Faceplate'
import type { Twin } from '../types'

const DeviceManager = lazy(() => import('./DeviceManager'))
const OsShell = lazy(() => import('./OsShell'))

const NET_GUIS = new Set(['netdevice', 'ngfw', 'adc'])

export function ShellRouter({ assetId, twin }: { assetId: string; twin: Twin }) {
  const [gui, setGui] = useState<string>('')
  const [dialect, setDialect] = useState('')
  const asset = twin.assets.find((a) => a.id === assetId)
  const devId = twin.devices?.find((d) => d.asset_id === assetId)?.device_id
  useEffect(() => {
    if (devId) api.device(devId).then((m) => { setGui(m.personality.gui); setDialect(m.personality.cli) }).catch(() => setGui('generic'))
    else setGui('generic')
  }, [devId])
  if (!asset) return <p className="p-3 text-xs">Asset not in twin.</p>
  return (
    <div className="p-3 space-y-3">
      <Faceplate twin={twin} assetId={assetId} />
      <Suspense fallback={<div className="skeleton h-40" />}>
        {NET_GUIS.has(gui)
          ? <DeviceManager assetId={assetId} twin={twin} dialect={dialect} />
          : gui.endsWith('server') || gui === 'hypervisor'
            ? <><DeviceManager assetId={assetId} twin={twin} dialect={dialect} /><OsShell assetId={assetId} twin={twin} gui={gui} dialect={dialect} /></>
            : <OsShell assetId={assetId} twin={twin} gui={gui || 'generic'} dialect={dialect} />}
      </Suspense>
      <p className="text-center font-mono text-[9px] text-slate-300">Emulated for simulation. Not affiliated with any vendor.</p>
    </div>
  )
}

export function useOpenDevice() {
  const { open } = useWindows()
  return (assetId: string, twin: Twin, name?: string) => {
    open(`device-${assetId}`, `${name ?? assetId} — device`, <ShellRouter assetId={assetId} twin={twin} />)
  }
}
