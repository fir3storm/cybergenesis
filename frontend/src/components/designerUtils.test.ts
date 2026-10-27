import { describe, expect, it } from 'vitest'
import { autoConfigPayload, autoHostname, mediaCompatible, portsFromManifest, validateConnection } from './designerUtils'

describe('designer utils', () => {
  it('expands manifest ports', () => {
    const ports = portsFromManifest([{ prefix: 'Gi', start: 1, count: 3, speed: '1G', media: 'copper' }])
    expect(ports.map((p) => p.name)).toEqual(['Gi1', 'Gi2', 'Gi3'])
  })
  it('refuses media mismatch and used ports', () => {
    const copper = { name: 'Gi1', speed: '1G', media: 'copper' }
    const sfp = { name: 'Te1', speed: '10G', media: 'sfp' }
    expect(mediaCompatible(copper, sfp)).toBe(false)
    expect(validateConnection(new Set(), 'a', copper, 'b', sfp)).toContain('media mismatch')
    expect(validateConnection(new Set(['a:Gi1']), 'a', copper, 'b', copper)).toContain('already cabled')
    expect(validateConnection(new Set(), 'a', copper, 'b', { ...copper, name: 'Gi2' })).toBeNull()
  })
  it('builds an auto-config payload for both ends and hostnames', () => {
    const p = autoConfigPayload('fw-01', 'port1', 'ws-01', 'eth0', false)
    expect(p.diff.ops.some((o) => o.value === 'to ws-01:eth0')).toBe(true)
    expect(autoHostname('Fortinet', ['FOR-01'])).toBe('FOR-02')
  })
})
