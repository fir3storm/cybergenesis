export interface PortInfo { name: string; speed: string; media: string }

export function portsFromManifest(ports: { prefix: string; start: number; count: number; speed: string; media: string }[]): PortInfo[] {
  const out: PortInfo[] = []
  for (const p of ports) for (let i = 0; i < p.count; i++) out.push({ name: `${p.prefix}${p.start + i}`, speed: p.speed, media: p.media })
  return out
}

export function mediaCompatible(a: PortInfo, b: PortInfo): boolean {
  return a.media === b.media || a.media === 'virtual' || b.media === 'virtual' || a.media === 'wifi' || b.media === 'wifi'
}

export function validateConnection(
  usedPorts: Set<string>,
  aId: string, aPort: PortInfo | null,
  bId: string, bPort: PortInfo | null,
): string | null {
  if (!aPort || !bPort) return 'pick a free port on both devices'
  if (usedPorts.has(`${aId}:${aPort.name}`)) return `port ${aId}:${aPort.name} is already cabled`
  if (usedPorts.has(`${bId}:${bPort.name}`)) return `port ${bId}:${bPort.name} is already cabled`
  if (!mediaCompatible(aPort, bPort)) return `media mismatch: ${aPort.media} vs ${bPort.media}`
  return null
}

/** Auto-config payload staged on both ends when a cable is created (Phase 2 config API ops). */
export function autoConfigPayload(deviceId: string, myPort: string, peerId: string, peerPort: string, routed: boolean) {
  return {
    diff: {
      ops: [
        { op: 'set', path: `interfaces.${myPort}.enabled`, value: true },
        { op: 'set', path: `interfaces.${myPort}.description`, value: `to ${peerId}:${peerPort}` },
        routed
          ? { op: 'set', path: `interfaces.${myPort}.mode`, value: 'routed' }
          : { op: 'set', path: `interfaces.${myPort}.mode`, value: 'access' },
        routed
          ? { op: 'set', path: `interfaces.${myPort}.ip`, value: 'auto-/30' }
          : { op: 'set', path: `interfaces.${myPort}.vlan`, value: 1 },
      ],
    },
    author: 'human',
    device: deviceId,
  }
}

export function autoHostname(vendorOrKind: string, existing: string[]): string {
  const prefix = vendorOrKind.replace(/[^A-Za-z]/g, '').slice(0, 3).toUpperCase() || 'DEV'
  let n = 1
  while (existing.includes(`${prefix}-${String(n).padStart(2, '0')}`)) n++
  return `${prefix}-${String(n).padStart(2, '0')}`
}
