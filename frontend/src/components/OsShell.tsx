import { useState } from 'react'
import { api } from '../services/api'
import type { Twin } from '../types'
import CliTerminal from './CliTerminal'

/** Lightweight OS shells. Every app reflects compiled twin state + live telemetry. */
export default function OsShell({ assetId, twin, gui, dialect }: { assetId: string; twin: Twin; gui: string; dialect: string }) {
  const [app, setApp] = useState('Desktop')
  const [msg, setMsg] = useState<string | null>(null)
  const asset = twin.assets.find((a) => a.id === assetId)
  const isWindows = gui.startsWith('windows')
  const isMac = gui.startsWith('macos')
  const isOt = gui === 'ot-hmi'
  const infected = asset?.status === 'compromised' || asset?.status === 'suspicious'
  const files = ['report.docx', 'budget.xlsx', 'notes.txt', 'photo.jpg'].map((f) => (infected && gui.includes('windows') ? `${f}.locked` : f))

  const kill = () => {
    api.twinAction?.('kill_process', assetId, {}).then(() => setMsg('kill_process applied via policy gate — twin updated.'))
      .catch((e) => setMsg(`kill refused: ${(e as Error).message}`))
  }
  return (
    <div className={`rounded-lg border p-3 ${isWindows ? 'border-sky-800 bg-gradient-to-b from-sky-950 to-slate-950' : isMac ? 'border-slate-600 bg-slate-900' : 'border-emerald-900 bg-slate-950'}`}>
      <div className="flex items-center justify-between">
        <b className="text-sm">{isOt ? '🕹 OT HMI' : isMac ? ' macOS' : isWindows ? '⊞ Windows' : '🐧 Linux / Server'} — {asset?.name}</b>
        <span className={`font-mono text-[10px] ${infected ? 'text-red-300' : 'text-emerald-300'}`}>{asset?.status.toUpperCase()}</span>
      </div>
      <div className="mt-2 flex gap-1">
        {['Desktop', 'Files', 'Task Manager', 'Event Viewer', 'Services', 'Users', 'Terminal', ...(gui === 'windows-server' ? ['BMC'] : []), ...(isOt ? ['Process Mimic', 'Alarms'] : [])].map((a) => (
          <button key={a} onClick={() => setApp(a)} className={`rounded px-2 py-1 text-[10px] ${app === a ? 'bg-cyan-600 text-white' : 'bg-slate-800'}`}>{a}</button>
        ))}
      </div>
      {msg && <p className="mt-1 text-[11px] text-cyan-300">{msg}</p>}
      <div className="mt-2 min-h-32 rounded bg-black/40 p-2 text-xs">
        {app === 'Desktop' && <p>Desktop of {asset?.name}. {infected ? '⚠ Suspicious activity detected by the twin — files are being renamed.' : 'All clear.'} Double-click apps above. Synthetic environment only.</p>}
        {app === 'Files' && <ul>{files.map((f) => <li key={f} className="font-mono">📄 {f}{f.endsWith('.locked') && <span className="text-red-300"> (encrypted by synthetic process)</span>}</li>)}</ul>}
        {app === 'Task Manager' && (
          <div><p className="font-mono">suspicious-synthetic.exe {infected ? '— RUNNING (high CPU)' : '— not present'}</p>
            {infected && <button onClick={kill} className="mt-1 rounded bg-red-600 px-2 py-1 text-[11px] font-bold">End task (kill_process)</button>}</div>
        )}
        {app === 'Event Viewer' && <pre className="font-mono text-[10px]">{`4624 Logon success (synthetic)\n${infected ? '4625 Logon failure x14 (synthetic)\n4688 Process created: suspicious-synthetic.exe' : '4688 Process created: explorer.exe'}`}</pre>}
        {app === 'Services' && <p>WinDefend / sshd / smb — start/stop stages a ConfigDiff via DeviceManager. (Read-only summary here.)</p>}
        {app === 'Users' && <p>Local users come from the device config (Users/AAA tab in DeviceManager for servers). Disable/reset actions map to revoke/rotate defenses.</p>}
        {app === 'Terminal' && <CliTerminal assetId={assetId} dialect={dialect || (isWindows ? 'powershell' : 'bash')} />}
        {app === 'BMC' && <p>🖥 BMC (synthetic): health OK · power ON · firmware 2.1 · virtual console available. Emulated for simulation. Not affiliated with any vendor.</p>}
        {app === 'Process Mimic' && <p>🛢 Tank level 62% · Pump P-101 RUN · Valves V1 open / V2 closed (synthetic process values, read-only).</p>}
        {app === 'Alarms' && <p>{infected ? '🔴 ALM-204: abnormal setpoint change (synthetic)' : 'No active alarms.'}</p>}
      </div>
    </div>
  )
}
