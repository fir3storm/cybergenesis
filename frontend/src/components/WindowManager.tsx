import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { Minus, Square, X } from 'lucide-react'

/** New windows size to the viewport: min(780, vw - 32), never exceeding it. */
export function responsiveWindowWidth(vw: number): number {
  return Math.min(780, Math.max(200, vw - 32))
}

export function clampWindowSize(w: number, h: number, vw: number, vh: number): { w: number; h: number } {
  return {
    w: Math.min(Math.max(w, Math.min(420, Math.max(240, vw - 32))), Math.max(240, vw - 16)),
    h: Math.min(Math.max(h, Math.min(300, Math.max(200, vh - 48))), Math.max(200, vh - 16)),
  }
}

function viewport(): { vw: number; vh: number } {
  return typeof window === 'undefined'
    ? { vw: 1024, vh: 768 }
    : { vw: window.innerWidth, vh: window.innerHeight }
}

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

/** Clamp a window so its title bar can never leave the viewport. Pure + tested. */
export function clampWindow(x: number, y: number, w: number, vw: number, vh: number): { x: number; y: number; w: number } {
  const width = Math.min(w, Math.max(320, vw - 16))
  return {
    w: width,
    x: Math.min(Math.max(x, -width + 90), Math.max(vw - 90, 0)),
    y: Math.min(Math.max(y, 0), Math.max(vh - 44, 0)),
  }
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
      const { vw, vh } = viewport()
      const w = responsiveWindowWidth(vw)
      const h = Math.min(540, Math.max(280, vh - 56))
      const pos = clampWindow(90 + n * 34, 70 + n * 28, w, vw, vh)
      return [...ws, { id, title, content, x: pos.x, y: pos.y, w, h, z: zRef.current, minimized: false, maximized: false }]
    })
    focus(id)
  }, [focus])

  // Keep every title bar on screen when the browser window itself resizes.
  useEffect(() => {
    const onResize = () => {
      const { vw, vh } = viewport()
      setWindows((ws) => ws.map((w) => {
        if (w.maximized) return w
        const size = clampWindowSize(Math.min(w.w, Math.max(240, vw - 16)), Math.min(w.h, Math.max(200, vh - 48)), vw, vh)
        const pos = clampWindow(w.x, w.y, size.w, vw, vh)
        return { ...w, x: pos.x, y: pos.y, w: size.w, h: size.h }
      }))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
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
              className={`max-w-44 truncate rounded px-2 py-1 text-[11px] ${w.minimized ? 'bg-slate-800/70 text-slate-300' : 'bg-cyan-950 text-cyan-200 border border-cyan-800'}`}>
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
  const update = (patch: Partial<WinState>) => setWindows((ws) => ws.map((x) => {
    if (x.id !== w.id) return x
    const merged = { ...x, ...patch }
    const c = clampWindow(merged.x, merged.y, merged.w, window.innerWidth, window.innerHeight)
    return { ...merged, x: c.x, y: c.y, w: c.w }
  }))
  return (
    <section style={style} className="flex flex-col overflow-hidden rounded-xl border border-cyan-900 bg-[#020617] shadow-[0_24px_70px_rgba(0,0,0,0.8)]"
      onMouseDown={() => focus(w.id)} aria-label={w.title}>
      <header className="flex cursor-move items-center gap-2 border-b border-slate-800 bg-slate-900 px-3 py-2"
        onMouseDown={(e) => { drag.current = { dx: e.clientX - w.x, dy: e.clientY - w.y } }}
        onMouseMove={(e) => {
          if (drag.current && !w.maximized) {
            const { vw, vh } = viewport()
            update(clampWindow(e.clientX - drag.current.dx, e.clientY - drag.current.dy, w.w, vw, vh))
          }
        }}
        onMouseUp={() => { drag.current = null }}>
        <span className="flex-1 truncate text-xs font-bold text-cyan-100">{w.title}</span>
        <span className="text-[9px] text-slate-300">Emulated for simulation. Not affiliated with any vendor.</span>
        <button aria-label="Minimise" onClick={() => update({ minimized: true })} className="rounded p-1 text-slate-200 hover:bg-slate-700"><Minus size={13} /></button>
        <button aria-label="Maximise" onClick={() => update({ maximized: !w.maximized })} className="rounded p-1 text-slate-200 hover:bg-slate-700"><Square size={12} /></button>
        <button aria-label="Close" onClick={() => close(w.id)} className="rounded p-1 text-slate-200 hover:bg-red-900"><X size={13} /></button>
      </header>
      <div className="min-h-0 flex-1 overflow-auto">{w.content}</div>
      {!w.maximized && (
        <div className="absolute bottom-0 right-0 h-4 w-4 cursor-se-resize"
          onMouseDown={(e) => { resize.current = { x: e.clientX, y: e.clientY, w: w.w, h: w.h } }}
          onMouseMove={(e) => {
            if (resize.current) {
              const { vw, vh } = viewport()
              const size = clampWindowSize(resize.current.w + e.clientX - resize.current.x, resize.current.h + e.clientY - resize.current.y, vw, vh)
              const pos = clampWindow(w.x, w.y, size.w, vw, vh)
              update({ ...size, ...pos })
            }
          }}
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
