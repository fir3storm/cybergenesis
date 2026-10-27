import { describe, expect, it } from 'vitest'
import { activeAttackPath, blockedEdgeIndex } from './status'
import type { RunResult, Twin } from '../types'

function resultsWith(metrics: Record<string, unknown>): RunResult {
  return {
    run: { id: 'r1', scenario_id: 'lateral_movement', seed: 42, state: 'COMPLETED', mode: 'offline', error: null, metrics: {} },
    verification: { outcome: 'PASS', invariant: 'x', checks: [], metrics },
    decisions: [], policy: [], executions: [],
  }
}

const twin: Twin = {
  assets: [
    { id: 'a', name: 'A', asset_type: 'workstation', zone: 'z', posture: 0.5, status: 'healthy', isolated: false, service_disabled: false, vulnerabilities: [], connected: ['b'], pos: [0, 1, 0] },
    { id: 'b', name: 'B', asset_type: 'workstation', zone: 'z', posture: 0.5, status: 'healthy', isolated: false, service_disabled: false, vulnerabilities: [], connected: ['a', 'c'], pos: [1, 1, 0] },
    { id: 'c', name: 'C', asset_type: 'database', zone: 'z', posture: 0.5, status: 'healthy', isolated: false, service_disabled: false, vulnerabilities: [], connected: ['b'], pos: [2, 1, 0] },
  ],
  connections: [
    { source: 'a', target: 'b', trust: 'medium', traversable: true, types: ['network'], active: true, dir_forward_active: true, dir_reverse_active: true },
    { source: 'b', target: 'c', trust: 'medium', traversable: true, types: ['network'], active: true, dir_forward_active: false, dir_reverse_active: true, one_way_blocked: true },
  ],
  identities: {}, containment: ['block_outbound:b->c'],
}

describe('activeAttackPath (F8b)', () => {
  it('falls back to the static table with no run data', () => {
    const a = activeAttackPath(null, 'lateral_movement')
    expect(a.source).toBe('static')
    expect(a.path[0]).toBe('internet')
    expect(a.blocked).toBe(false)
  })

  it('prefers the latest red-team round path and reports blocked', () => {
    const a = activeAttackPath(resultsWith({
      after_reachable_or_granted: false,
      baseline_path: ['internet', 'firewall', 'database'],
      after_path: null,
      rounds: [{ round: 1, path: ['internet', 'firewall', 'database'] }, { round: 2, path: ['employee-workstation', 'app-server', 'database'] }],
    }), 'lateral_movement')
    expect(a.source).toBe('round')
    expect(a.round).toBe(2)
    expect(a.path).toEqual(['employee-workstation', 'app-server', 'database'])
    expect(a.blocked).toBe(true)
  })

  it('ignores a run belonging to a different builtin scenario', () => {
    const a = activeAttackPath(resultsWith({ baseline_path: ['internet', 'firewall', 'database'] }), 'ransomware_activity')
    expect(a.source).toBe('static')
    expect(a.path).toEqual(['employee-workstation', 'file-server'])
  })

  it('uses after_path, then baseline_path, when no rounds exist', () => {
    expect(activeAttackPath(resultsWith({ after_path: ['x', 'y'], baseline_path: ['a', 'b'] }), 'nope').path).toEqual(['x', 'y'])
    const b = activeAttackPath(resultsWith({ after_path: null, baseline_path: ['a', 'b'], after_reachable_or_granted: false }), 'nope')
    expect(b.path).toEqual(['a', 'b'])
    expect(b.blocked).toBe(true)
  })
})

describe('blockedEdgeIndex (F8b)', () => {
  it('finds the one-way blocked hop in the travelled direction', () => {
    expect(blockedEdgeIndex(['a', 'b', 'c'], twin)).toBe(1)
    // reverse travel over the same connection is not blocked that way
    expect(blockedEdgeIndex(['c', 'b', 'a'], twin)).toBe(-1)
  })

  it('treats isolation as a blocked hop and open chains as unblocked', () => {
    const iso: Twin = { ...twin, assets: twin.assets.map((a) => (a.id === 'b' ? { ...a, isolated: true } : a)) }
    expect(blockedEdgeIndex(['a', 'b', 'c'], iso)).toBe(0)
    expect(blockedEdgeIndex(['a', 'b'], twin)).toBe(-1)
    expect(blockedEdgeIndex(['a'], twin)).toBe(-1)
  })
})
