import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import type { Asset, Twin } from '../types'
import { useStore } from '../stores/store'

export const REDUCED_MOTION = typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches

export { STATUS_COLOR } from './status'
import { STATUS_COLOR } from './status'

const SHORT_LABEL: Record<string, string> = {
  internet: 'Internet', firewall: 'Firewall', 'web-server': 'Web Server', 'app-server': 'App Server',
  database: 'Database', 'identity-provider': 'Identity Provider', 'admin-workstation': 'Admin Workstation',
  'employee-workstation': 'Employee Workstation', 'file-server': 'File Server', 'security-sensor': 'Security Sensor',
}
/** Front-row labels go below their node, back-row above — prevents centre pile-up. */
const LABEL_BELOW = new Set(['employee-workstation', 'file-server', 'admin-workstation', 'app-server'])

function Node({ a }: { a: Asset }) {
  const ref = useRef<THREE.Mesh>(null)
  const [hovered, setHovered] = useState(false)
  const set = useStore((s) => s.set)
  const selected = useStore((s) => s.selectedAsset === a.id)
  const color = STATUS_COLOR[a.status] ?? '#22d3ee'
  const expanded = selected || hovered
  const below = LABEL_BELOW.has(a.id)
  useFrame(({ clock }) => {
    if (ref.current && !REDUCED_MOTION) {
      ref.current.position.y = a.pos[1] + Math.sin(clock.elapsedTime * 1.2 + a.pos[0]) * 0.08
      ref.current.rotation.y = clock.elapsedTime * 0.25
    }
  })
  return (
    <group position={a.pos}>
      <mesh ref={ref}
        onClick={(e) => { e.stopPropagation(); set({ selectedAsset: a.id }) }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true) }}
        onPointerOut={() => setHovered(false)}>
        {a.asset_type === 'database' ? <cylinderGeometry args={[0.4, 0.4, 0.66, 24]} />
          : a.asset_type === 'firewall' || a.asset_type === 'gateway' ? <boxGeometry args={[0.7, 0.7, 0.7]} />
          : <octahedronGeometry args={[0.44]} />}
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={selected ? 2.2 : 1.1} metalness={0.6} roughness={0.25} />
      </mesh>
      {(a.status === 'contained' || a.status === 'remediated') && (
        <mesh rotation={[Math.PI / 2.4, 0, 0]}>
          <torusGeometry args={[0.8, 0.035, 10, 48]} />
          <meshStandardMaterial color="#34d399" emissive="#34d399" emissiveIntensity={1.6} transparent opacity={0.85} />
        </mesh>
      )}
      {selected && (
        <mesh><sphereGeometry args={[1.0, 24, 24]} /><meshBasicMaterial color={color} wireframe transparent opacity={0.25} /></mesh>
      )}
      <Html distanceFactor={18} position={[0, below ? -0.92 : 0.92, 0]} center zIndexRange={[10, 0]}>
        <div style={{
          color: '#e2e8f0', fontSize: expanded ? 11 : 9.5, fontFamily: 'monospace', textAlign: 'center',
          pointerEvents: 'none', whiteSpace: 'nowrap', background: 'rgba(2,6,23,0.78)',
          border: `1px solid ${expanded ? color : 'rgba(100,116,139,0.45)'}`,
          borderRadius: 999, padding: expanded ? '3px 8px' : '2px 6px', lineHeight: 1.35,
        }}>
          <span style={{ color }}>●</span> {SHORT_LABEL[a.id] ?? a.name}
          {expanded && <><br /><span style={{ color, fontSize: 9 }}>{a.status.toUpperCase()} · {a.zone}</span></>}
        </div>
      </Html>
    </group>
  )
}

function Traffic({ from, to, active, attack }: { from: [number, number, number]; to: [number, number, number]; active: boolean; attack: boolean }) {
  const ref = useRef<THREE.Mesh>(null)
  const a = useMemo(() => new THREE.Vector3(...from), [from])
  const b = useMemo(() => new THREE.Vector3(...to), [to])
  useFrame(({ clock }) => {
    if (ref.current) {
      const t = REDUCED_MOTION ? 0.5 : (clock.elapsedTime * 0.35 + from[0] * 0.1) % 1
      ref.current.position.lerpVectors(a, b, t)
    }
  })
  if (!active) return null
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[0.09, 10, 10]} />
      <meshBasicMaterial color={attack ? '#ef4444' : '#22d3ee'} />
    </mesh>
  )
}

export const ATTACK_PATHS: Record<string, string[]> = {
  ransomware_activity: ['employee-workstation', 'file-server'],
  compromised_identity: ['admin-workstation', 'database'],
  lateral_movement: ['internet', 'firewall', 'web-server', 'app-server', 'database'],
}

/** Keyboard nav: arrows orbit, +/- zoom, Enter selects most severe asset, Esc clears.
 * Identical state is also available as text via the asset list (accessible alternative). */
function KeyboardNav({ twin }: { twin: Twin }) {
  const { camera } = useThree()
  const set = useStore((s) => s.set)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      const sph = new THREE.Spherical().setFromVector3(camera.position.clone())
      if (e.key === 'ArrowLeft') sph.theta -= 0.18
      else if (e.key === 'ArrowRight') sph.theta += 0.18
      else if (e.key === 'ArrowUp') sph.phi = Math.max(0.15, sph.phi - 0.12)
      else if (e.key === 'ArrowDown') sph.phi = Math.min(1.5, sph.phi + 0.12)
      else if (e.key === '+' || e.key === '=') sph.radius = Math.max(5, sph.radius - 1)
      else if (e.key === '-') sph.radius = Math.min(24, sph.radius + 1)
      else if (e.key === 'Enter') {
        const rank: Record<string, number> = { compromised: 5, suspicious: 4, exposed: 3, contained: 2, remediated: 1, healthy: 0 }
        const worst = [...twin.assets].sort((x, y) => (rank[y.status] ?? 0) - (rank[x.status] ?? 0))[0]
        if (worst) set({ selectedAsset: worst.id })
        return
      } else if (e.key === 'Escape') { set({ selectedAsset: null }); return } else return
      camera.position.setFromSpherical(sph)
      camera.lookAt(0, 1.2, 0)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [camera, twin, set])
  return null
}

export default function TwinScene({ twin }: { twin: Twin }) {
  const scenarioId = useStore((s) => s.scenarioId)
  const pos = useMemo(() => Object.fromEntries(twin.assets.map((a) => [a.id, a.pos])), [twin])
  const path = ATTACK_PATHS[scenarioId] ?? []
  const onPath = (s: string, t: string) => {
    const i = path.indexOf(s)
    return i >= 0 && path[i + 1] === t || (path.indexOf(t) >= 0 && path[path.indexOf(t) + 1] === s)
  }
  return (
    <Canvas camera={{ position: [0, 7.5, 15], fov: 50 }} style={{ background: 'radial-gradient(ellipse at center, #0a1628 0%, #020617 70%)' }}
      aria-label="Interactive 3D digital twin. Use the asset list for keyboard access to the same information.">
      <ambientLight intensity={0.5} />
      <pointLight position={[6, 8, 6]} intensity={60} color="#22d3ee" />
      <pointLight position={[-6, 4, -4]} intensity={30} color="#2563eb" />
      <gridHelper args={[24, 28, '#164e63', '#0f2537']} position={[0, -0.6, 0]} />
      {twin.connections.map((c) => {
        const attack = onPath(c.source, c.target)
        const col = !c.active ? '#334155' : attack ? '#ef4444' : c.traversable ? '#155e75' : '#1e3a5f'
        return (
          <group key={`${c.source}-${c.target}`}>
            <Line points={[pos[c.source], pos[c.target]]} color={col} lineWidth={attack ? 3 : 1.2} transparent opacity={c.active ? 0.95 : 0.35} />
            <Traffic from={pos[c.source]} to={pos[c.target]} active={c.active} attack={attack} />
          </group>
        )
      })}
      {twin.assets.map((a) => <Node key={a.id} a={a} />)}
      <KeyboardNav twin={twin} />
      <OrbitControls enableDamping makeDefault />
    </Canvas>
  )
}
