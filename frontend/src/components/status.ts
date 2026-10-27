import type { RunResult, Twin } from '../types'

export const ATTACK_PATHS: Record<string, string[]> = {
  ransomware_activity: ['employee-workstation', 'file-server'],
  compromised_identity: ['admin-workstation', 'database'],
  lateral_movement: ['internet', 'firewall', 'web-server', 'app-server', 'database'],
  data_exfiltration: ['database', 'app-server', 'web-server', 'firewall', 'internet'],
  red_vs_blue_battle: ['internet', 'firewall', 'web-server', 'app-server', 'file-server'],
}

export const STATUS_COLOR: Record<string, string> = {
  healthy: '#22d3ee', exposed: '#f59e0b', suspicious: '#fb923c',
  compromised: '#ef4444', contained: '#38bdf8', recovering: '#a78bfa', remediated: '#34d399', protected: '#22c55e', cleared: '#7dd3fc',
}

function stringPath(value: unknown): string[] | null {
  if (!Array.isArray(value) || value.length === 0) return null
  return value.every((v) => typeof v === 'string') ? (value as string[]) : null
}

export interface ActiveAttackPath {
  path: string[]
  /** round number when the path comes from the latest red-team round, else null */
  round: number | null
  /** true when the verification says the objective is no longer reachable */
  blocked: boolean
  source: 'round' | 'after' | 'baseline' | 'static'
}

/**
 * The attack chain for the ACTIVE run: the current (latest) red-team round's
 * path wins, then the verified after/baseline paths from the latest
 * verification metrics. The static ATTACK_PATHS table is only a fallback
 * when no run data exists.
 */
export function activeAttackPath(results: RunResult | null, scenarioId: string): ActiveAttackPath {
  const metrics = results?.verification?.metrics
  const blocked = metrics?.after_reachable_or_granted === false
  // A completed run for a DIFFERENT builtin scenario is not the active run
  // for the scenario now selected — fall back to that scenario's table.
  const runScenario = results?.run.scenario_id
  const foreignRun = Boolean(runScenario && runScenario !== scenarioId
    && runScenario in ATTACK_PATHS && scenarioId in ATTACK_PATHS)
  if (metrics && !foreignRun) {
    const rounds = Array.isArray(metrics.rounds) ? metrics.rounds : []
    for (let i = rounds.length - 1; i >= 0; i--) {
      const r = rounds[i]
      if (r && typeof r === 'object') {
        const rec = r as Record<string, unknown>
        const p = stringPath(rec.path)
        if (p) return { path: p, round: typeof rec.round === 'number' ? rec.round : i + 1, blocked, source: 'round' }
      }
    }
    const after = stringPath(metrics.after_path)
    if (after) return { path: after, round: null, blocked, source: 'after' }
    const baseline = stringPath(metrics.baseline_path)
    if (baseline) return { path: baseline, round: null, blocked, source: 'baseline' }
  }
  return { path: ATTACK_PATHS[scenarioId] ?? [], round: null, blocked, source: 'static' }
}

/**
 * Index of the first hop (path[i] -> path[i+1]) that cannot carry traffic in
 * the given twin: connection missing/inactive in that direction, or either
 * endpoint isolated. -1 when every hop is open. A one-way (egress/ingress)
 * block counts for the direction the chain actually travels.
 */
export function blockedEdgeIndex(path: string[], twin: Twin | null): number {
  if (!twin || path.length < 2) return -1
  const byId = new Map(twin.assets.map((a) => [a.id, a]))
  for (let i = 0; i < path.length - 1; i++) {
    const s = path[i]
    const t = path[i + 1]
    if (byId.get(s)?.isolated || byId.get(t)?.isolated) return i
    const conn = twin.connections.find((c) => (c.source === s && c.target === t) || (c.source === t && c.target === s))
    if (!conn || !conn.traversable) return i
    const forward = conn.source === s // chain travels conn.source -> conn.target
    const dirActive = forward ? conn.dir_forward_active : conn.dir_reverse_active
    if (dirActive !== undefined ? !dirActive : !conn.active) return i
  }
  return -1
}
