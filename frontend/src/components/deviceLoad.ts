/**
 * Deterministic synthetic CPU/memory load derived from twin status (F8c #3).
 *
 * There is no real telemetry — these values are synthetic and labelled as
 * such in the UI. Derivation is a pure function of the asset status (plus a
 * small deterministic per-asset jitter so sibling devices do not all show
 * identical numbers): compromised → high, contained/suspicious → medium,
 * healthy/remediated → low.
 */

export interface SyntheticLoad {
  cpu: number
  memory: number
}

const BASE: Record<string, SyntheticLoad> = {
  compromised: { cpu: 92, memory: 87 },
  suspicious: { cpu: 64, memory: 66 },
  exposed: { cpu: 34, memory: 42 },
  contained: { cpu: 48, memory: 55 },
  recovering: { cpu: 38, memory: 48 },
  healthy: { cpu: 18, memory: 34 },
  remediated: { cpu: 15, memory: 30 },
  protected: { cpu: 16, memory: 32 },
  cleared: { cpu: 14, memory: 29 },
}

function jitter(assetId: string | undefined, salt: number): number {
  if (!assetId) return 0
  let h = salt
  for (let i = 0; i < assetId.length; i++) h = (h * 31 + assetId.charCodeAt(i)) % 997
  return (h % 7) - 3 // deterministic -3..+3
}

export function syntheticLoad(status: string | undefined, assetId?: string): SyntheticLoad {
  const base = BASE[status ?? ''] ?? { cpu: 22, memory: 36 }
  return {
    cpu: Math.min(99, Math.max(2, base.cpu + jitter(assetId, 7))),
    memory: Math.min(99, Math.max(2, base.memory + jitter(assetId, 13))),
  }
}
