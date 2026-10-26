import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import { Bloom, EffectComposer, Vignette } from '@react-three/postprocessing'
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

function NodeShape({ a, color, selected }: { a: Asset; color: string; selected: boolean }) {
  const mat = <meshStandardMaterial color={color} emissive={color} emissiveIntensity={selected ? 2.4 : 1.25} metalness={0.65} roughness={0.22} />
  switch (a.asset_type) {
    case 'database': // disk stack
      return <group>{[-0.24, 0, 0.24].map((y) => (
        <mesh key={y} position={[0, y, 0]}><cylinderGeometry args={[0.42, 0.42, 0.18, 24]} />{mat}</mesh>))}</group>
    case 'firewall': // router cone / shield wedge
      return <mesh><coneGeometry args={[0.52, 0.85, 5]} />{mat}</mesh>
    case 'gateway':
      return <mesh><torusGeometry args={[0.42, 0.16, 12, 28]} />{mat}</mesh>
    case 'identity': // orb
      return <mesh><sphereGeometry args={[0.42, 24, 24]} />{mat}</mesh>
    case 'sensor': // radar tetra
      return <mesh><tetrahedronGeometry args={[0.55]} />{mat}</mesh>
    case 'workstation': // terminal block + screen slab
      return <group>
        <mesh><boxGeometry args={[0.62, 0.42, 0.5]} />{mat}</mesh>
        <mesh position={[0, 0.38, -0.08]} rotation={[-0.25, 0, 0]}><boxGeometry args={[0.55, 0.34, 0.05]} />{mat}</mesh>
      </group>
    case 'file_server':
      return <mesh><boxGeometry args={[0.5, 0.72, 0.5]} />{mat}</mesh>
    case 'web_server':
    case 'app_server':
      return <mesh><octahedronGeometry args={[0.46]} />{mat}</mesh>
    default:
      return <mesh><octahedronGeometry args={[0.44]} />{mat}</mesh>
  }
}

function Node({ a }: { a: Asset }) {
  const ref = useRef<THREE.Group>(null)
  const shellRef = useRef<THREE.Mesh>(null)
  const lightRef = useRef<THREE.PointLight>(null)
  const pulseRef = useRef<THREE.Mesh>(null)
  const ringRef = useRef<THREE.Mesh>(null)
  const ringStart = useRef(-1)
  const curColor = useRef(new THREE.Color(STATUS_COLOR[a.status] ?? '#22d3ee'))
  useEffect(() => { ringStart.current = -1 }, [a.status])
  const [hovered, setHovered] = useState(false)
  const set = useStore((s) => s.set)
  const selected = useStore((s) => s.selectedAsset === a.id)
  const color = STATUS_COLOR[a.status] ?? '#22d3ee'
  const expanded = selected || hovered
  const below = LABEL_BELOW.has(a.id)
  const compromised = a.status === 'compromised' || a.status === 'suspicious'
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    // smooth status colour transition (~0.5s lerp toward target)
    curColor.current.lerp(new THREE.Color(color), REDUCED_MOTION ? 1 : 0.08)
    if (ref.current) {
      ref.current.traverse((o) => {
        const mesh = o as THREE.Mesh
        const m = mesh.material as THREE.MeshStandardMaterial | undefined
        if (mesh.isMesh && m && 'emissive' in m) { m.color.copy(curColor.current); m.emissive.copy(curColor.current) }
      })
    }
    if (shellRef.current) {
      const sm = shellRef.current.material as THREE.MeshBasicMaterial
      sm.color.copy(curColor.current)
    }
    if (ringRef.current) { // containment ring: expands 0.6 -> 1.25 -> 1 on becoming contained/remediated
      if (ringStart.current < 0) ringStart.current = t
      const p = Math.min((t - ringStart.current) / 1.1, 1)
      const s = REDUCED_MOTION ? 1 : 0.6 + Math.sin(p * Math.PI * 0.72) * 0.65 * (1 - p * 0.35)
      ringRef.current.scale.setScalar(Math.max(s, 0.6))
    }
    if (ref.current && !REDUCED_MOTION) {
      ref.current.position.y = a.pos[1] + Math.sin(t * 1.2 + a.pos[0]) * 0.08
      ref.current.rotation.y = t * 0.25
    }
    if (shellRef.current) { // holographic shell breathes; expands on hover/select
      const target = expanded ? 1.45 : 1.12
      const cur = shellRef.current.scale.x
      const next = REDUCED_MOTION ? target : cur + (target - cur) * 0.12
      shellRef.current.scale.setScalar(next)
    }
    if (lightRef.current) { // per-node glow; compromised nodes pulse hard
      lightRef.current.intensity = compromised && !REDUCED_MOTION ? 9 + Math.sin(t * 5) * 5 : selected ? 12 : 6
    }
    if (pulseRef.current) { // expanding alarm ring on compromised/suspicious
      if (compromised && !REDUCED_MOTION) {
        const s = 1 + (t % 1.4) / 1.4 * 1.6
        pulseRef.current.scale.setScalar(s)
        const m = pulseRef.current.material as THREE.MeshBasicMaterial
        m.opacity = Math.max(0, 0.65 - (t % 1.4) / 1.4 * 0.65)
      }
    }
  })
  return (
    <group position={a.pos}>
      <pointLight ref={lightRef} color={color} intensity={6} distance={5.5} decay={1.8} />
      <group ref={ref}
        onClick={(e) => { e.stopPropagation(); set({ selectedAsset: a.id }) }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true) }}
        onPointerOut={() => setHovered(false)}>
        <NodeShape a={a} color={color} selected={selected} />
      </group>
      {/* holographic wireframe shell */}
      <mesh ref={shellRef}>
        <icosahedronGeometry args={[0.72, 1]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={expanded ? 0.5 : 0.22} />
      </mesh>
      {compromised && (
        <mesh ref={pulseRef} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.85, 0.02, 8, 48]} />
          <meshBasicMaterial color="#ef4444" transparent opacity={0.6} />
        </mesh>
      )}
      {(a.status === 'contained' || a.status === 'remediated') && (
        <mesh ref={ringRef} rotation={[Math.PI / 2.4, 0, 0]}>
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
          boxShadow: `0 0 ${expanded ? 16 : 9}px ${color}66, inset 0 0 8px ${color}22`,
          backdropFilter: 'blur(3px)',
        }}>
          <span style={{ color }}>●</span> {SHORT_LABEL[a.id] ?? a.name}
          {expanded && <><br /><span style={{ color, fontSize: 9 }}>{a.status.toUpperCase()} · {a.zone}</span></>}
        </div>
      </Html>
    </group>
  )
}

const PARTICLES_PER_EDGE = 4

function TrafficParticle({ a, b, offset, attack }: { a: THREE.Vector3; b: THREE.Vector3; offset: number; attack: boolean }) {
  const ref = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    if (ref.current) {
      const t = REDUCED_MOTION ? (offset + 0.2) % 1 : (clock.elapsedTime * (attack ? 0.55 : 0.3) + offset) % 1
      ref.current.position.lerpVectors(a, b, t) // direction: source -> target (attack flows toward the target)
      const s = attack ? 1 + Math.sin(clock.elapsedTime * 6 + offset * 9) * 0.35 : 1
      ref.current.scale.setScalar(REDUCED_MOTION ? 1 : s)
    }
  })
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[attack ? 0.11 : 0.075, 10, 10]} />
      <meshBasicMaterial color={attack ? '#ef4444' : '#22d3ee'} />
    </mesh>
  )
}

function Traffic({ from, to, active, attack }: { from: [number, number, number]; to: [number, number, number]; active: boolean; attack: boolean }) {
  const a = useMemo(() => new THREE.Vector3(...from), [from])
  const b = useMemo(() => new THREE.Vector3(...to), [to])
  if (!active) return null
  return (
    <group>
      {Array.from({ length: PARTICLES_PER_EDGE }, (_, i) => (
        <TrafficParticle key={i} a={a} b={b} offset={i / PARTICLES_PER_EDGE + from[0] * 0.03} attack={attack} />
      ))}
    </group>
  )
}

const WAVE_VERT = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`
const WAVE_FRAG = `uniform float uTime; uniform vec3 uColor; varying vec2 vUv;
void main(){
  float wave = pow(0.5 + 0.5 * sin((vUv.y * 14.0 - uTime * 4.5) * 6.2831), 3.0);
  float edge = smoothstep(0.0, 0.25, vUv.y) * smoothstep(1.0, 0.75, vUv.y);
  gl_FragColor = vec4(uColor * (0.35 + wave * 1.6), (0.12 + wave * 0.75) * edge);
}`

/** Animated energy wave travelling source -> target along an attack-path edge. */
function WaveEdge({ from, to }: { from: [number, number, number]; to: [number, number, number] }) {
  const { mid, len, quat, mat } = useMemo(() => {
    const a = new THREE.Vector3(...from); const b = new THREE.Vector3(...to)
    const dir = b.clone().sub(a); const length = dir.length()
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
    const m = new THREE.ShaderMaterial({
      uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color('#ef4444') } },
      vertexShader: WAVE_VERT, fragmentShader: WAVE_FRAG,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
    })
    return { mid: a.add(b).multiplyScalar(0.5), len: length, quat: q, mat: m }
  }, [from, to])
  useFrame(({ clock }) => { mat.uniforms.uTime.value = REDUCED_MOTION ? 0.4 : clock.elapsedTime })
  return (
    <mesh position={mid} quaternion={quat} material={mat}>
      <cylinderGeometry args={[0.09, 0.09, len, 10, 1, true]} />
    </mesh>
  )
}

export const ATTACK_PATHS: Record<string, string[]> = {
  ransomware_activity: ['employee-workstation', 'file-server'],
  compromised_identity: ['admin-workstation', 'database'],
  lateral_movement: ['internet', 'firewall', 'web-server', 'app-server', 'database'],
  data_exfiltration: ['database', 'app-server', 'web-server', 'firewall', 'internet'],
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
            <Line points={[pos[c.source], pos[c.target]]} color={col} lineWidth={attack ? 3.5 : 1.2} transparent opacity={c.active ? 0.95 : 0.35} />
            {attack && c.active && <WaveEdge from={pos[c.source]} to={pos[c.target]} />}
            <Traffic from={pos[c.source]} to={pos[c.target]} active={c.active} attack={attack} />
          </group>
        )
      })}
      {twin.assets.map((a) => <Node key={a.id} a={a} />)}
      <KeyboardNav twin={twin} />
      <OrbitControls enableDamping makeDefault />
      <EffectComposer>
        <>
          <Bloom intensity={0.85} luminanceThreshold={0.18} luminanceSmoothing={0.32} mipmapBlur />
          <Vignette eskil={false} offset={0.22} darkness={0.62} />
        </>
      </EffectComposer>
    </Canvas>
  )
}
