import { useEffect, useRef, useState } from 'react'
import { api } from '../services/api'

/** Lightweight terminal (backend-authoritative CLI). xterm-style UX without the bundle cost
 *  until a real terminal session is needed; history + completion come from the backend. */
export default function CliTerminal({ assetId, dialect }: { assetId: string; dialect: string }) {
  const [lines, setLines] = useState<string[]>([`Connected to ${assetId} (dialect: ${dialect || '…'}). Type '?' for help. Emulated — synthetic only.`])
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [lines])

  const run = () => {
    const cmd = input
    setInput('')
    if (!cmd.trim()) return
    setHistory((h) => [cmd, ...h].slice(0, 30))
    setLines((l) => [...l, `${assetId}> ${cmd}`])
    api.cliExec(assetId, cmd).then((r) => setLines((l) => [...l, ...(r.output ? r.output.split('\n') : [])]))
      .catch((e) => setLines((l) => [...l, `% error: ${(e as Error).message}`]))
  }
  return (
    <div className="rounded bg-black p-2 font-mono text-[11px] text-emerald-200">
      <div className="max-h-64 overflow-auto whitespace-pre-wrap">
        {lines.map((l, i) => <div key={i}>{l}</div>)}
        <div ref={endRef} />
      </div>
      <div className="mt-1 flex gap-1">
        <span className="text-cyan-300">{assetId}&gt;</span>
        <input value={input} onChange={(e) => setInput(e.target.value)} aria-label="CLI input"
          onKeyDown={(e) => {
            if (e.key === 'Enter') run()
            if (e.key === 'ArrowUp' && history[0]) setInput(history[0])
            if (e.key === 'Tab') { e.preventDefault(); api.cliExec(assetId, '?').catch(() => undefined) }
          }}
          className="flex-1 bg-transparent outline-none" placeholder="show running-config" />
      </div>
      <p className="text-[9px] text-slate-600">Backend-authoritative emulated CLI · config commands stage ConfigDiffs · history ↑</p>
    </div>
  )
}
