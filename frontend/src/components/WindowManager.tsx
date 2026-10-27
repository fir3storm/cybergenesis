import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { Minus, Square, X } from 'lucide-react'

export interface WinState {
  id: string
  title: string
  content: ReactNode
  x: number; y: number; w: number; h: number
  z: number
  minimized: boolean
  maximized: boolean
}

interface WM {
  windows: WinState[]
  open: (id: string, title: string, content: ReactNode) => void
  close: (id: string) => void
  focus: (id: string) => void
}

const Ctx = createContext<WM>({ windows: [], open: () => undefined, close: () => undefined, focus: () => undefined })
export const useWindows = () => useContext(Ctx)

export function WindowManagerProvider({ children }: { children: ReactNode }) {
  const [windows, setWindows] = useState<WinState[]>([])
  const zRef = useRef(10)

  const focus = useCallback((id: string) => {
    zRef.current += 1
    const z = zRef.current
    setWindows((ws) => ws.map((w) => (w.id === id ? { ...w, z, minimized: false } : w)))
  }, [])
  const open = useCallback((id: string, title: string, content: ReactNode) => {
    setWindows((ws) => {
      if (ws.some((w) => w.id === id)) return ws
      zRef.current += 1
      const n = ws.length
      return [...ws, { id, title, content, x: 90 + n * 34, y: 70 + n * 28, w: 780, h: 540, z: zRef.current, minimized: false, maximized: false }]
    })
    focus(id)
  }, [focus])
  const close = useCallback((id: string) => setWindows((ws) => ws.filter((w) => w.id !== id)), [])

  return (
    <Ctx.Provider value={{ windows, open, close, focus }}>
      {children}
      {windows.filter((w) => !w.minimized).map((w) => (
        <DraggableWindow key={w.id} w={w} windows={windows} setWindows={setWindows} close={close} focus={focus} />
      ))}
      {windows.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 z-[90] flex gap-1 border-t border-slate-800 bg-[#020617] px-2 py-1">
          {windows.map((w) => (
            <button key={w.id} onClick={() => focus(w.id)}
              className={`max-w-44 truncate rounded px-2 py-1 text-[11px] ${w.minimized ? 'text-slate-500' : 'bg-cyan-950 text-cyan-200 border border-cyan-800'}`}>
              {w.title}</button>
          ))}
        </div>
      )}
    </Ctx.Provider>
  )
}

function DraggableWindow({ w, setWindows, close, focus }: {
  w: WinState
  windows: WinState[]
  setWindows: React.Dispatch<React.SetStateAction<WinState[]>>
  close: (id: string) => void
  focus: (id: string) => void
}) {
  const drag = useRef<{ dx: number; dy: number } | null>(null)
  const resize = useRef<{ x: number; y: number; w: number; h: number } | null>(null)
  const style: React.CSSProperties = w.maximized
    ? { position: 'fixed', inset: 8, zIndex: w.z }
    : { position: 'fixed', left: w.x, top: w.y, width: w.w, height: w.h, zIndex: w.z }
  const update = (patch: Partial<WinState>) => setWindows((ws) => ws.map((x) => (x.id === w.id ? { ...x, ...patch } : x)))
  return (
    <section style={style} className="flex flex-col overflow-hidden rounded-xl border border-cyan-900 bg-[#020617] shadow-[0_24px_70px_rgba(0,0,0,0.8)]"
      onMouseDown={() => focus(w.id)} aria-label={w.title}>
      <header className="flex cursor-move items-center gap-2 border-b border-slate-800 bg-slate-900 px-3 py-2"
        onMouseDown={(e) => { drag.current = { dx: e.clientX - w.x, dy: e.clientY - w.y } }}
        onMouseMove={(e) => { if (drag.current && !w.maximized) update({ x: e.clientX - drag.current.dx, y: Math.max(0, e.clientY - drag.current.dy) }) }}
        onMouseUp={() => { drag.current = null }}>
        <span className="flex-1 truncate text-xs font-bold text-cyan-100">{w.title}</span>
        <span className="text-[9px] text-slate-500">Emulated for simulation. Not affiliated with any vendor.</span>
        <button aria-label="Minimise" onClick={() => update({ minimized: true })} className="rounded p-1 hover:bg-slate-700"><Minus size={13} /></button>
        <button aria-label="Maximise" onClick={() => update({ maximized: !w.maximized })} className="rounded p-1 hover:bg-slate-700"><Square size={12} /></button>
        <button aria-label="Close" onClick={() => close(w.id)} className="rounded p-1 hover:bg-red-900"><X size={13} /></button>
      </header>
      <div className="min-h-0 flex-1 overflow-auto">{w.content}</div>
      {!w.maximized && (
        <div className="absolute bottom-0 right-0 h-4 w-4 cursor-se-resize"
          onMouseDown={(e) => { resize.current = { x: e.clientX, y: e.clientY, w: w.w, h: w.h } }}
          onMouseMove={(e) => { if (resize.current) update({ w: Math.max(420, resize.current.w + e.clientX - resize.current.x), h: Math.max(300, resize.current.h + e.clientY - resize.current.y) }) }}
          onMouseUp={() => { resize.current = null }} />
      )}
    </section>
  )
}

export function useEscapeClose() {
  const { windows, close } = useWindows()
  return useCallback(() => {
    const top = [...windows].filter((w) => !w.minimized).sort((a, b) => b.z - a.z)[0]
    if (top) close(top.id)
  }, [windows, close])
}
