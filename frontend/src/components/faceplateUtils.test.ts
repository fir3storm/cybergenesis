import { describe, expect, it } from 'vitest'
import { faceplateGrid, ledColor, linkStateForPort } from './faceplateUtils'
import { syntheticLoad } from './deviceLoad'

describe('faceplate LED mapping (F8c)', () => {
  it('maps live link states to LED colours', () => {
    expect(ledColor('up', false)).toBe('#22c55e')
    expect(ledColor('filtered', false)).toBe('#f59e0b')
    expect(ledColor('down', false)).toBe('#ef4444')
    expect(ledColor(undefined, false)).toBe('#475569')
  })

  it('forces down when the asset is isolated, whatever the link says', () => {
    expect(ledColor('up', true)).toBe('#ef4444')
    expect(linkStateForPort([{ peer: 'a', state: 'up' }], 0, true)).toBe('down')
  })

  it('never cycles links onto unrelated ports', () => {
    const links = [{ peer: 'a', state: 'up' }]
    expect(linkStateForPort(links, 0, false)).toBe('up')
    expect(linkStateForPort(links, 5, false)).toBeUndefined()
  })

  it('shows all ports of a 28-port flagship switch in a compact grid', () => {
    const g = faceplateGrid(28)
    expect(g.rows * g.perRow).toBeGreaterThanOrEqual(28)
    expect(g.rows).toBe(2)
    expect(g.step).toBeLessThan(44)
    expect(faceplateGrid(4).step).toBe(44)
    expect(faceplateGrid(1).perRow).toBe(1)
  })
})

describe('syntheticLoad (F8c)', () => {
  it('derives deterministic load bands from twin status', () => {
    const compromised = syntheticLoad('compromised', 'db-1')
    const contained = syntheticLoad('contained', 'db-1')
    const healthy = syntheticLoad('healthy', 'db-1')
    expect(compromised.cpu).toBeGreaterThan(contained.cpu)
    expect(contained.cpu).toBeGreaterThan(healthy.cpu)
    expect(compromised.memory).toBeGreaterThan(healthy.memory)
    expect(syntheticLoad('compromised', 'db-1')).toEqual(compromised)
  })

  it('stays in range for unknown statuses', () => {
    const l = syntheticLoad('mystery', 'x')
    expect(l.cpu).toBeGreaterThanOrEqual(2)
    expect(l.cpu).toBeLessThanOrEqual(99)
  })
})
