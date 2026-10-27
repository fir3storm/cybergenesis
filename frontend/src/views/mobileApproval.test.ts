import { describe, expect, it } from 'vitest'
import { qrDataUrl } from './mobileApproval'

describe('qrDataUrl', () => {
  it('renders a QR image for the mobile approval URL', () => {
    const url = qrDataUrl('http://192.168.1.20:8000/m/approve/run-123?t=one-time-token')
    expect(url.startsWith('data:image/')).toBe(true)
    expect(url.length).toBeGreaterThan(200)
  })
  it('encodes different tokens into different codes', () => {
    expect(qrDataUrl('http://192.168.1.20:8000/m/approve/r?t=aaa'))
      .not.toBe(qrDataUrl('http://192.168.1.20:8000/m/approve/r?t=bbb'))
  })
})
