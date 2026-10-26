import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import type { Asset, Twin } from '../types'
import { useStore } from '../stores/store'

export const STATUS_COLOR: Record<string, string> = {
  healthy: '#22d3ee', exposed: '#f59e0b', suspicious: '#fb923c',
  compromised: '#ef4444', contained: '#38bdf8', recovering: '#a78bfa', remediated: '#34d399',
}

function Node({ a }: { a: Asset }) {
  const ref = useRef<THREE.Mesh>(null)
  const set = useStore((s) => s.set)
  const selected = useStore((s) => s.selectedAsset === a.id)
  const color = STATUS_COLOR[a.status] ?? '#22d3ee'
  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.position.y = a.pos[1] + Math.sin(clock.elapsedTime * 1.2 + a.pos[0]) * 0.08
      ref.current.rotation.y = clock.elapsedTime * 0.25
    }
  })
  return (
    <group position={a.pos}>
      <mesh ref={ref} onClick={(e) => { e.stopPropagation(); set({ selectedAsset: a.id }) }}>
        {a.asset_type === 'database' ? <cylinderGeometry args={[0.42, 0.42, 0.7, 24]} />
          : a.asset_type === 'firewall' || a.asset_type === 'gateway' ? <boxGeometry args={[0.75, 0.75, 0.75]} />
          : <octahedronGeometry args={[0.48]} />}
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={selected ? 2.2 : 1.1} metalness={0.6} roughness={0.25} />
      </mesh>
      {(a.status === 'contained' || a.status === 'remediated') && (
        <mesh rotation={[Math.PI / 2.4, 0, 0]}>
          <torusGeometry args={[0.85, 0.035, 10, 48]} />
          <meshStandardMaterial color="#34d399" emissive="#34d399" emissiveIntensity={1.6} transparent opacity={0.85} />
        </mesh>
      )}
      {selected && (
        <mesh><sphereGeometry args={[1.05, 24, 24]} /><meshBasicMaterial color={color} wireframe transparent opacity={0.25} /></mesh>
      )}
      <Html distanceFactor={16} position={[0, 0.95, 0]} center>
        <div style={{ color: '#e2e8f0', fontSize: 11, fontFamily: 'monospace', textAlign: 'center', pointerEvents: 'none', textShadow: '0 0 8px #000', whiteSpace: 'nowrap' }}>
          {a.name}<br /><span style={{ color }}>{a.status.toUpperCase()}</span>
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
      const t = (clock.elapsedTime * 0.35 + from[0] * 0.1) % 1
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

export default function TwinScene({ twin }: { twin: Twin }) {
  const scenarioId = useStore((s) => s.scenarioId)
  const pos = useMemo(() => Object.fromEntries(twin.assets.map((a) => [a.id, a.pos])), [twin])
  const path = ATTACK_PATHS[scenarioId] ?? []
  const onPath = (s: string, t: string) => {
    const i = path.indexOf(s)
    return i >= 0 && path[i + 1] === t || (path.indexOf(t) >= 0 && path[path.indexOf(t) + 1] === s)
  }
  return (
    <Canvas camera={{ position: [0, 6.5, 11], fov: 52 }} style={{ background: 'radial-gradient(ellipse at center, #0a1628 0%, #020617 70%)' }}
      aria-label="Interactive 3D digital twin. Use the asset list for keyboard access to the same information.">
      <ambientLight intensity={0.5} />
      <pointLight position={[6, 8, 6]} intensity={60} color="#22d3ee" />
      <pointLight position={[-6, 4, -4]} intensity={30} color="#2563eb" />
      <gridHelper args={[18, 24, '#164e63', '#0f2537']} position={[0, -0.6, 0]} />
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
      <OrbitControls enableDamping makeDefault />
    </Canvas>
  )
}
