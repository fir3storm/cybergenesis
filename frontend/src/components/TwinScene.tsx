import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Bounds, Html, Instances, Instance, Line, OrbitControls } from '@react-three/drei'
import { Bloom, ChromaticAberration, EffectComposer, Vignette } from '@react-three/postprocessing'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { Asset, Conn, Twin } from '../types'
import { useStore } from '../stores/store'
import { ATTACK_PATHS, STATUS_COLOR } from './status'
import { NODE_LAYOUT, ZONES, ZONE_OF, layoutFor } from './zones'

export { ATTACK_PATHS } from './status'
export { STATUS_COLOR } from './status'

export const REDUCED_MOTION = typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const SHORT_LABEL: Record<string, string> = {
  internet: 'Internet', firewall: 'Firewall', 'web-server': 'Web Server', 'app-server': 'App Server',
  database: 'Database', 'identity-provider': 'Identity Provider', 'admin-workstation': 'Admin Workstation',
  'employee-workstation': 'Employee Workstation', 'file-server': 'File Server', 'security-sensor': 'Security Sensor',
}

function statusColor(a: Asset): string {
  if (a.isolated) return '#94a3b8'
  return STATUS_COLOR[a.status] ?? '#22d3ee'
}

/* ---------------- icons (one coherent pedestal + icon per node) ---------------- */

function NodeIcon({ type, color }: { type: string; color: string }) {
  const mat = <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.15} metalness={0.55} roughness={0.3} toneMapped={false} />
  switch (type) {
    case 'database':
      return <group>{[-0.17, 0.02, 0.21].map((y) => <mesh key={y} position={[0, y, 0]}><cylinderGeometry args={[0.34, 0.34, 0.15, 20]} />{mat}</mesh>)}</group>
    case 'firewall':
      return <mesh><coneGeometry args={[0.42, 0.68, 6]} />{mat}</mesh>
    case 'gateway':
      return <mesh><sphereGeometry args={[0.34, 14, 10]} /><meshBasicMaterial color={color} wireframe transparent opacity={0.85} /></mesh>
    case 'identity':
      return <group><mesh><sphereGeometry args={[0.2, 16, 16]} />{mat}</mesh><mesh position={[0.24, -0.22, 0]} rotation={[0, 0, -0.7]}><boxGeometry args={[0.1, 0.3, 0.1]} />{mat}</mesh></group>
    case 'sensor':
      return <group><mesh><tetrahedronGeometry args={[0.4]} />{mat}</mesh><mesh rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.52, 0.02, 8, 32]} /><meshBasicMaterial color={color} transparent opacity={0.6} /></mesh></group>
    case 'workstation':
      return <group><mesh position={[0, 0.05, 0]}><boxGeometry args={[0.52, 0.36, 0.04]} />{mat}</mesh><mesh position={[0, -0.2, 0.05]}><boxGeometry args={[0.4, 0.05, 0.24]} />{mat}</mesh></group>
    case 'file_server':
      return <mesh><boxGeometry args={[0.42, 0.58, 0.42]} />{mat}</mesh>
    default:
      return <mesh><octahedronGeometry args={[0.36]} />{mat}</mesh>
  }
}

/* ---------------- node ---------------- */

interface NodeProps {
  a: Asset
  dimmed: boolean
  protectedTarget: boolean
  links: string[]
}

function Node({ a, dimmed, protectedTarget, links }: NodeProps) {
  const set = useStore((s) => s.set)
  const selected = useStore((s) => s.selectedAsset === a.id)
  const [hovered, setHovered] = useState(false)
  const iconRef = useRef<THREE.Group>(null)
  const lightRef = useRef<THREE.PointLight>(null)
  const ringRef = useRef<THREE.Mesh>(null)
  const protStart = useRef(-1)
  const cur = useRef(new THREE.Color(statusColor(a)))
  const [x, topY, z] = layoutFor(a.id, a.pos)
  const color = statusColor(a)
  const compromised = a.status === 'compromised'
  const suspicious = a.status === 'suspicious' || a.status === 'exposed'
  const expanded = selected || hovered

  useEffect(() => { if (!protectedTarget) protStart.current = -1 }, [protectedTarget])

  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    const target = new THREE.Color(color)
    if (dimmed) target.multiplyScalar(0.3)
    cur.current.lerp(target, REDUCED_MOTION ? 1 : 0.07)
    iconRef.current?.traverse((o) => {
      const mesh = o as THREE.Mesh
      const m = mesh.material as THREE.MeshStandardMaterial | undefined
      if (mesh.isMesh && m && 'emissive' in m) { m.color.copy(cur.current); m.emissive.copy(cur.current) }
    })
    if (iconRef.current && !REDUCED_MOTION) {
      const pulse = compromised ? 1 + Math.sin(t * 6) * 0.13 : suspicious ? 1 + Math.sin(t * 2.2) * 0.07 : 1
      iconRef.current.scale.setScalar(pulse)
      iconRef.current.rotation.y = t * 0.3
    }
    if (lightRef.current) {
      lightRef.current.color.copy(cur.current)
      lightRef.current.intensity = compromised ? (REDUCED_MOTION ? 10 : 10 + Math.sin(t * 6) * 5) : selected ? 8 : dimmed ? 0.8 : 3.5
    }
    if (ringRef.current) { // target ring turns green over ~1.2s once containment blocks the path
      const m = ringRef.current.material as THREE.MeshStandardMaterial
      if (protectedTarget) {
        if (protStart.current < 0) protStart.current = t
        const p = Math.min((t - protStart.current) / 1.2, 1)
        m.color.lerpColors(new THREE.Color('#64748b'), new THREE.Color('#22c55e'), REDUCED_MOTION ? 1 : p)
        m.emissive.copy(m.color)
      } else {
        m.color.copy(cur.current); m.emissive.copy(cur.current)
      }
    }
  })

  return (
    <group position={[x, 0, z]}>
      {/* pedestal */}
      <mesh position={[0, 0.22, 0]}>
        <cylinderGeometry args={[0.52, 0.62, 0.44, 24]} />
        <meshStandardMaterial color="#0b2237" metalness={0.7} roughness={0.25} transparent opacity={dimmed ? 0.45 : 0.92} />
      </mesh>
      <mesh ref={ringRef} position={[0, 0.46, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.55, 0.025, 8, 40]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.4} toneMapped={false} />
      </mesh>
      {a.isolated && ( // dashed cage for blocked/isolated
        <Line points={Array.from({ length: 33 }, (_, i) => {
          const th = (i / 32) * Math.PI * 2
          return [Math.cos(th) * 0.78, 0.85, Math.sin(th) * 0.78] as [number, number, number]
        })} color="#94a3b8" lineWidth={1.4} dashed dashSize={0.16} gapSize={0.12} transparent opacity={0.9} />
      )}
      <pointLight ref={lightRef} position={[0, 1.3, 0]} color={color} intensity={3.5} distance={5} decay={1.8} />
      <group ref={iconRef} position={[0, topY + 0.35, 0]}
        onClick={(e) => { e.stopPropagation(); set({ selectedAsset: a.id }) }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true) }}
        onPointerOut={() => setHovered(false)}>
        <NodeIcon type={a.asset_type} color={color} />
      </group>
      {a.status === 'remediated' && (
        <Html position={[0.55, topY + 0.75, 0]} center zIndexRange={[20, 0]}>
          <div style={{ background: '#22c55e', color: '#04160a', borderRadius: 999, width: 18, height: 18, fontSize: 12, fontWeight: 900, textAlign: 'center', lineHeight: '18px', pointerEvents: 'none', boxShadow: '0 0 10px #22c55e88' }}>✓</div>
        </Html>
      )}
      <Html distanceFactor={17} position={[0, topY + 1.05, 0]} center occlude zIndexRange={[15, 0]}>
        <div style={{
          color: '#e2e8f0', fontSize: expanded ? 11 : 9.5, fontFamily: 'monospace', textAlign: 'center', pointerEvents: 'none',
          whiteSpace: 'nowrap', background: 'rgba(2,6,23,0.8)', border: `1px solid ${color}`, borderRadius: 999,
          padding: '2px 7px', lineHeight: 1.4, opacity: dimmed && !expanded ? 0.55 : 1,
          boxShadow: `0 0 ${expanded ? 15 : 8}px ${color}55`,
        }}>
          {SHORT_LABEL[a.id] ?? a.name}{' '}
          <span style={{ color, fontWeight: 700 }}>{(a.isolated ? 'ISOLATED' : a.status).toUpperCase()}</span>
        </div>
      </Html>
      {hovered && (
        <Html position={[0, topY + 1.85, 0]} center zIndexRange={[30, 0]}>
          <div style={{ background: 'rgba(2,6,23,0.94)', border: '1px solid #155e75', borderRadius: 10, padding: '8px 10px', color: '#e2e8f0', fontSize: 11, fontFamily: 'monospace', width: 210, pointerEvents: 'none' }}>
            <b>{a.name}</b><br />
            Role: {a.asset_type} · Zone: {ZONE_OF[a.id] ?? a.zone}<br />
            Status: <span style={{ color }}>{a.status}</span> · Posture {(a.posture * 100).toFixed(0)}%<br />
            Vulnerabilities: {a.vulnerabilities.length ? a.vulnerabilities.join(', ') : 'none'}<br />
            Connections: {links.join(', ') || 'none'}
          </div>
        </Html>
      )}
    </group>
  )
}

/* ---------------- edges ---------------- */

function edgeCurve(s: [number, number, number], t: [number, number, number]): THREE.QuadraticBezierCurve3 {
  const a = new THREE.Vector3(s[0], 0.95, s[2])
  const b = new THREE.Vector3(t[0], 0.95, t[2])
  const mid = a.clone().add(b).multiplyScalar(0.5); mid.y = 1.55
  return new THREE.QuadraticBezierCurve3(a, mid, b)
}

function EdgeTube({ s, t, attack, dimmed }: { s: [number, number, number]; t: [number, number, number]; attack: boolean; dimmed: boolean }) {
  const geo = useMemo(() => new THREE.TubeGeometry(edgeCurve(s, t), 20, attack ? 0.045 : 0.014, 6), [s, t, attack])
  return (
    <mesh geometry={geo}>
      <meshBasicMaterial color={attack ? '#f97316' : '#2dd4bf'} transparent
        opacity={attack ? 0.95 : dimmed ? 0.05 : 0.32} toneMapped={false} />
    </mesh>
  )
}

function BlockedEdge({ s, t }: { s: [number, number, number]; t: [number, number, number] }) {
  const curve = edgeCurve(s, t)
  const pts = useMemo(() => curve.getPoints(24), [curve])
  const mid = curve.getPoint(0.5)
  return (
    <group>
      <Line points={pts} color="#ef4444" lineWidth={2} dashed dashSize={0.22} gapSize={0.16} transparent opacity={0.95} />
      <group position={mid}>
        <Line points={[[-0.22, -0.22, 0], [0.22, 0.22, 0]]} color="#ef4444" lineWidth={3.5} />
        <Line points={[[-0.22, 0.22, 0], [0.22, -0.22, 0]]} color="#ef4444" lineWidth={3.5} />
      </group>
    </group>
  )
}

/* ---------------- attack particle flow (instanced) ---------------- */

interface FlowProps { chain: string[]; positions: Map<string, [number, number, number]>; stopPoint: THREE.Vector3 | null }

function AttackFlow({ chain, positions, stopPoint }: FlowProps) {
  const refs = useRef<(THREE.Object3D | null)[]>([])
  const curves = useMemo(() => {
    const out: THREE.QuadraticBezierCurve3[] = []
    for (let i = 0; i < chain.length - 1; i++) {
      const s = positions.get(chain[i]); const t = positions.get(chain[i + 1])
      if (s && t) out.push(edgeCurve(s, t))
    }
    return out
  }, [chain, positions])
  const PER = 4
  const total = curves.length * PER
  const lengths = useMemo(() => curves.map((c) => c.getLength()), [curves])
  const totalLen = lengths.reduce((a, b) => a + b, 0) || 1
  const stopDist = useMemo(() => {
    if (!stopPoint) return null
    let acc = 0
    for (let i = 0; i < curves.length; i++) {
      if (curves[i].getPoint(0.99).distanceTo(stopPoint) < 1.2 || curves[i].getPoint(0.5).distanceTo(stopPoint) < 0.6) return acc + lengths[i] * 0.55
      acc += lengths[i]
    }
    return acc
  }, [curves, lengths, stopPoint])

  useFrame(({ clock }) => {
    const time = REDUCED_MOTION ? 0 : clock.elapsedTime
    for (let k = 0; k < total; k++) {
      const obj = refs.current[k]
      if (!obj) continue
      let d = (time * 1.5 + (k / Math.max(total, 1)) * totalLen) % totalLen
      if (stopDist !== null) d = Math.min(d, stopDist) // particles pile up and stop at the blocked edge
      let seg = 0; let rem = d
      while (seg < curves.length - 1 && rem > lengths[seg]) { rem -= lengths[seg]; seg++ }
      const p = curves[seg]?.getPoint(Math.min(rem / (lengths[seg] || 1), 1))
      if (p) obj.position.copy(p)
      obj.scale.setScalar(stopDist !== null && d >= stopDist - 0.01 ? 0.65 : 1)
    }
  })
  if (!curves.length || REDUCED_MOTION) return null
  return (
    <group>
      <Instances limit={Math.max(total, 1)} range={total}>
        <sphereGeometry args={[0.085, 10, 10]} />
        <meshBasicMaterial color="#fb923c" toneMapped={false} />
        {Array.from({ length: total }, (_, k) => (
          <Instance key={k} ref={(o: THREE.Object3D | null) => { refs.current[k] = o }} />
        ))}
      </Instances>
      {curves.map((c, i) => { // arrowhead at each segment end, pointing at the target
        const end = c.getPoint(0.97); const tan = c.getTangent(0.97)
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), tan)
        return <mesh key={i} position={end} quaternion={q}><coneGeometry args={[0.13, 0.34, 10]} /><meshBasicMaterial color="#ef4444" toneMapped={false} /></mesh>
      })}
    </group>
  )
}

/* ---------------- camera ---------------- */

function CameraRig({ positions, resetNonce, zoomCmd, chain }: {
  positions: Map<string, [number, number, number]>
  resetNonce: number
  zoomCmd: { dir: 1 | -1; n: number } | null
  chain: string[]
}) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null
  const selected = useStore((s) => s.selectedAsset)
  const cinematicMode = useStore((s) => s.cinematicMode)
  const goal = useRef<{ target: THREE.Vector3; cam: THREE.Vector3 } | null>(null)

  useEffect(() => { // cinematic: camera follows the attack path node by node
    if (!cinematicMode || chain.length < 2) return
    let i = 0
    const tick = () => {
      const p = positions.get(chain[i % chain.length])
      if (p) goal.current = { target: new THREE.Vector3(p[0], 1, p[2]), cam: new THREE.Vector3(p[0] + 2.6, 2.8, p[2] + 3.6) }
      i++
    }
    tick()
    const iv = window.setInterval(tick, 2400)
    return () => window.clearInterval(iv)
  }, [cinematicMode, chain, positions])

  useEffect(() => { // overview on mount / reset
    goal.current = { target: new THREE.Vector3(0, 0.7, 0), cam: new THREE.Vector3(9.2, 7.8, 11.2) }
  }, [resetNonce])
  useEffect(() => { // +/- zoom buttons: step toward (dir=1) or away (dir=-1) from current target
    if (!zoomCmd || !controls) return
    const offset = camera.position.clone().sub(controls.target)
    const factor = zoomCmd.dir === 1 ? 0.72 : 1.38
    const len = THREE.MathUtils.clamp(offset.length() * factor, 4.5, 30)
    offset.setLength(len)
    goal.current = { target: controls.target.clone(), cam: controls.target.clone().add(offset) }
  }, [zoomCmd]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (selected && positions.has(selected)) {
      const p = positions.get(selected)!
      goal.current = { target: new THREE.Vector3(p[0], 1, p[2]), cam: new THREE.Vector3(p[0] + 3.2, 3.4, p[2] + 4.2) }
    }
  }, [selected, positions])
  useEffect(() => {
    if (!controls) return
    const stop = () => { goal.current = null }
    controls.addEventListener('start', stop)
    return () => controls.removeEventListener('start', stop)
  }, [controls])

  useFrame(() => {
    if (!goal.current || !controls) return
    const k = REDUCED_MOTION ? 1 : 0.06
    controls.target.lerp(goal.current.target, k)
    camera.position.lerp(goal.current.cam, k)
    controls.update()
    if (camera.position.distanceTo(goal.current.cam) < 0.08) goal.current = null
  })
  return null
}

/** Keyboard: arrows orbit, +/- zoom, Enter selects most severe asset, Esc clears. */
function KeyboardNav({ assets }: { assets: Asset[] }) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null
  const set = useStore((s) => s.set)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'Enter') {
        const rank: Record<string, number> = { compromised: 5, suspicious: 4, exposed: 3, contained: 2, remediated: 1, healthy: 0 }
        const worst = [...assets].sort((x, y) => (rank[y.status] ?? 0) - (rank[x.status] ?? 0))[0]
        if (worst) set({ selectedAsset: worst.id })
        return
      }
      if (e.key === 'Escape') { set({ selectedAsset: null }); return }
      if (!controls) return
      const sph = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target))
      if (e.key === 'ArrowLeft') sph.theta -= 0.18
      else if (e.key === 'ArrowRight') sph.theta += 0.18
      else if (e.key === 'ArrowUp') sph.phi = Math.max(0.15, sph.phi - 0.12)
      else if (e.key === 'ArrowDown') sph.phi = Math.min(1.5, sph.phi + 0.12)
      else if (e.key === '+' || e.key === '=') sph.radius = Math.max(5, sph.radius - 1)
      else if (e.key === '-') sph.radius = Math.min(30, sph.radius + 1)
      else return
      camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(sph))
      controls.update()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [camera, controls, assets, set])
  return null
}

function DemandInvalidator({ twin }: { twin: Twin }) {
  const invalidate = useThree((s) => s.invalidate)
  const selected = useStore((s) => s.selectedAsset)
  useEffect(() => { invalidate() }, [twin, selected, invalidate])
  return null
}

/* ---------------- path helpers ---------------- */

function findPath(twin: Twin, src: string, dst: string): string[] | null {
  const active = new Map<string, Conn>()
  twin.connections.forEach((c) => { active.set(`${c.source}|${c.target}`, c); active.set(`${c.target}|${c.source}`, c) })
  const isolated = new Map(twin.assets.map((a) => [a.id, a.isolated]))
  if (isolated.get(src) || isolated.get(dst)) return null
  const prev = new Map<string, string | null>([[src, null]])
  const q = [src]
  while (q.length) {
    const n = q.shift()!
    if (n === dst) break
    for (const c of twin.connections) {
      const nb = c.source === n ? c.target : c.target === n ? c.source : null
      if (!nb || prev.has(nb) || !c.active || !c.traversable || isolated.get(nb)) continue
      prev.set(nb, n); q.push(nb)
    }
  }
  if (!prev.has(dst)) return null
  const path = [dst]
  let cur = dst
  while (cur !== src) { cur = prev.get(cur)!; path.unshift(cur) }
  void active
  return path
}

/* ---------------- scene ---------------- */

export default function TwinScene({ twin }: { twin: Twin }) {
  const scenarioId = useStore((s) => s.scenarioId)
  const mapFocus = useStore((s) => s.mapFocus)
  const set = useStore((s) => s.set)
  const [resetNonce, setResetNonce] = useState(0)
  const [zoomCmd, setZoomCmd] = useState<{ dir: 1 | -1; n: number } | null>(null)
  const zoom = (dir: 1 | -1) => setZoomCmd((prev) => ({ dir, n: (prev?.n ?? 0) + 1 }))

  const positions = useMemo(() => new Map(twin.assets.map((a) => [a.id, layoutFor(a.id, a.pos)] as [string, [number, number, number]])), [twin])
  const chain = ATTACK_PATHS[scenarioId] ?? []
  const livePath = chain.length >= 2 ? findPath(twin, chain[0], chain[chain.length - 1]) : null
  const displayChain = livePath ?? chain
  const pathNodes = new Set(displayChain)
  const pathEdges = new Set<string>()
  for (let i = 0; i < displayChain.length - 1; i++) { pathEdges.add(`${displayChain[i]}|${displayChain[i + 1]}`); pathEdges.add(`${displayChain[i + 1]}|${displayChain[i]}`) }
  const explicitBlocked = new Set(twin.containment.filter((c) => c.startsWith('block:')).map((c) => c.slice(6)))
  const isBlockedEdge = (c: Conn) => !c.active && (explicitBlocked.has(`${c.source}->${c.target}`) || explicitBlocked.has(`${c.target}->${c.source}`))
  const blockedOnChain = displayChain.length >= 2 && !livePath
    ? displayChain.slice(0, -1).map((id, i) => ({ s: id, t: displayChain[i + 1] })).find(({ s, t }) => {
        const c = twin.connections.find((x) => (x.source === s && x.target === t) || (x.source === t && x.target === s))
        return c && (!c.active || twin.assets.find((a) => a.id === s)?.isolated || twin.assets.find((a) => a.id === t)?.isolated)
      }) ?? null
    : null
  const stopPoint = blockedOnChain ? edgeCurve(positions.get(blockedOnChain.s)!, positions.get(blockedOnChain.t)!).getPoint(0.55) : null
  const targetProtected = Boolean(chain.length >= 2 && !livePath && twin.containment.length > 0)
  const anyCompromised = twin.assets.some((a) => a.status === 'compromised')
  const linksOf = (a: Asset) => twin.connections.filter((c) => c.source === a.id || c.target === a.id)
    .map((c) => (c.source === a.id ? c.target : c.source)).map((id) => SHORT_LABEL[id] ?? id)

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <Canvas frameloop={REDUCED_MOTION ? 'demand' : 'always'}
        camera={{ position: [9.2, 7.8, 11.2], fov: 50 }}
        style={{ background: '#050b16' }}
        aria-label="Interactive 3D digital twin. Use the asset list for keyboard access to the same information.">
        <fog attach="fog" args={['#050b16', 20, 38]} />
        <ambientLight intensity={0.55} />
        <pointLight position={[6, 9, 6]} intensity={50} color="#22d3ee" />
        <pointLight position={[-7, 5, -5]} intensity={24} color="#2563eb" />
        <gridHelper args={[30, 36, '#134a5e', '#0a2436']} position={[0, -0.02, 0]} />
        <Bounds fit clip margin={1.02}>
          <group key={resetNonce}>
            {ZONES.map((zoneDef) => (
              <group key={zoneDef.id}>
                <mesh position={[zoneDef.x, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                  <planeGeometry args={[3.5, 6.4]} />
                  <meshBasicMaterial color={zoneDef.color} transparent opacity={0.05} depthWrite={false} />
                </mesh>
                <Html position={[zoneDef.x, 0.12, -3.45]} center zIndexRange={[5, 0]}>
                  <div style={{ color: zoneDef.color, fontSize: 9, fontFamily: 'monospace', letterSpacing: 1.5, whiteSpace: 'nowrap', opacity: 0.85, pointerEvents: 'none' }}>{zoneDef.label}</div>
                </Html>
              </group>
            ))}
            {twin.connections.map((c) => {
              const s = positions.get(c.source); const t = positions.get(c.target)
              if (!s || !t) return null
              const key = `${c.source}-${c.target}`
              if (isBlockedEdge(c)) return <BlockedEdge key={key} s={s} t={t} />
              const attack = pathEdges.has(`${c.source}|${c.target}`)
              return <EdgeTube key={key} s={s} t={t} attack={attack} dimmed={mapFocus && !attack} />
            })}
            {displayChain.length >= 2 && <AttackFlow chain={displayChain} positions={positions} stopPoint={stopPoint} />}
            {twin.assets.map((a) => (
              <Node key={a.id} a={a} dimmed={mapFocus && !pathNodes.has(a.id)}
                protectedTarget={targetProtected && a.id === chain[chain.length - 1]} links={linksOf(a)} />
            ))}
          </group>
        </Bounds>
        <CameraRig positions={positions} resetNonce={resetNonce} zoomCmd={zoomCmd} chain={displayChain} />
        <KeyboardNav assets={twin.assets} />
        <DemandInvalidator twin={twin} />
        <OrbitControls enableDamping makeDefault maxPolarAngle={Math.PI * 0.49} minDistance={4} maxDistance={30} />
        <EffectComposer>
          <>
            <Bloom intensity={0.8} luminanceThreshold={0.6} luminanceSmoothing={0.3} mipmapBlur />
            {anyCompromised && !REDUCED_MOTION
              ? <ChromaticAberration offset={new THREE.Vector2(0.00045, 0.00045)} radialModulation={false} modulationOffset={0.15} />
              : <></>}
            <Vignette eskil={false} offset={0.2} darkness={0.6} />
          </>
        </EffectComposer>
      </Canvas>

      {/* camera controls: reset + zoom in/out */}
      <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 5 }} className="flex items-center gap-1.5">
        <button onClick={() => zoom(1)} aria-label="Zoom in" title="Zoom in"
          className="flex h-8 w-8 items-center justify-center rounded-full border border-cyan-800 bg-slate-950/80 text-base font-bold text-cyan-200 backdrop-blur hover:bg-slate-800">+</button>
        <button onClick={() => zoom(-1)} aria-label="Zoom out" title="Zoom out"
          className="flex h-8 w-8 items-center justify-center rounded-full border border-cyan-800 bg-slate-950/80 text-base font-bold text-cyan-200 backdrop-blur hover:bg-slate-800">−</button>
        <button onClick={() => { set({ selectedAsset: null }); setResetNonce((n) => n + 1) }}
          className="rounded-full border border-cyan-800 bg-slate-950/80 px-3 py-1.5 text-[11px] text-cyan-200 backdrop-blur hover:bg-slate-800">
          ⟲ Reset view
        </button>
      </div>

      {/* legend overlay */}
      <div className="glass-panel" style={{ position: 'absolute', left: 10, bottom: 10, zIndex: 5, borderRadius: 12, border: '1px solid rgba(21,94,117,0.6)', padding: '8px 10px', fontSize: 10, fontFamily: 'monospace', color: '#cbd5e1', lineHeight: 1.7, pointerEvents: 'none' }}>
        <div><span style={{ color: '#22d3ee' }}>●</span> healthy&nbsp; <span style={{ color: '#f59e0b' }}>●</span> suspicious (pulse)&nbsp; <span style={{ color: '#ef4444' }}>●</span> compromised (fast pulse)</div>
        <div><span style={{ color: '#22c55e' }}>● ✓</span> remediated&nbsp; <span style={{ color: '#94a3b8' }}>▭ dashed</span> blocked / isolated</div>
        <div><span style={{ color: '#2dd4bf' }}>─</span> normal edge&nbsp; <span style={{ color: '#f97316' }}>━▶</span> attack path (particles → target)&nbsp; <span style={{ color: '#ef4444' }}>- - ✕</span> blocked edge</div>
        <div style={{ color: '#7dd3fc' }}>{ZONES.map((zoneDef) => zoneDef.label).join('  ·  ')}</div>
      </div>
    </div>
  )
}

export { NODE_LAYOUT }
