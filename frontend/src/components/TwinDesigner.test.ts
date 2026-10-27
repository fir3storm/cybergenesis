import { describe, expect, it } from 'vitest'
import { FLAGSHIP_SWITCH_IDS, TEMPLATES } from './TwinDesigner'

describe('designer templates use catalog devices (F8c)', () => {
  it('has five templates, each carrying a catalog device_id on every asset', () => {
    expect(Object.keys(TEMPLATES)).toHaveLength(5)
    for (const t of Object.values(TEMPLATES)) {
      expect(t.assets.length).toBeGreaterThanOrEqual(4)
      for (const a of t.assets) {
        expect(a.device_id).toBeTruthy()
        expect(a.device_id).toMatch(/^[a-z0-9-]+$/)
      }
      for (const [x, y] of t.links) {
        expect(t.assets[x]).toBeTruthy()
        expect(t.assets[y]).toBeTruthy()
      }
    }
  })

  it('puts a flagship switch in the enterprise and data-centre templates', () => {
    const flagship = new Set<string>(FLAGSHIP_SWITCH_IDS)
    for (const name of ['Three-tier enterprise', 'Data-centre spine-leaf']) {
      expect(TEMPLATES[name].assets.some((a) => flagship.has(a.device_id))).toBe(true)
    }
    expect(TEMPLATES['Three-tier enterprise'].assets.map((a) => a.device_id)).toContain('cisco-catalyst-9300-48p')
  })
})
