import { describe, expect, it } from 'vitest'
import { computeLabelOffsets, LABEL_STEP } from './labelLayout'

const asset = (id: string, zone: string, z: number, x = 0) => ({ id, zone, pos: [x, 1, z] as [number, number, number] })

describe('computeLabelOffsets (F8c)', () => {
  it('staggers labels in the same zone by z order and never hides them', () => {
    const m = computeLabelOffsets([asset('b', 'edge', 2), asset('a', 'edge', -1), asset('c', 'edge', 5)])
    expect(m.get('a')).toEqual({ offset: 0, tier: 0 })
    expect(m.get('b')).toEqual({ offset: LABEL_STEP, tier: 1 })
    expect(m.get('c')).toEqual({ offset: LABEL_STEP * 2, tier: 2 })
    expect(m.size).toBe(3)
  })

  it('starts each zone at zero and is deterministic regardless of input order', () => {
    const first = computeLabelOffsets([asset('a', 'edge', 1), asset('b', 'data', 1), asset('c', 'edge', 2)])
    const shuffled = computeLabelOffsets([asset('c', 'edge', 2), asset('b', 'data', 1), asset('a', 'edge', 1)])
    expect(first.get('b')?.offset).toBe(0)
    expect(shuffled.get('a')).toEqual(first.get('a'))
    expect(shuffled.get('c')).toEqual(first.get('c'))
  })
})
