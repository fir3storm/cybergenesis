import { describe, expect, it } from 'vitest'
import { clampWindow } from './WindowManager'

describe('clampWindow', () => {
  it('keeps the title bar reachable at the right/bottom edges', () => {
    const c = clampWindow(5000, 5000, 780, 1440, 900)
    expect(c.x).toBeLessThanOrEqual(1440 - 90)
    expect(c.y).toBeLessThanOrEqual(900 - 44)
  })
  it('keeps at least 90px visible on the left/top', () => {
    const c = clampWindow(-5000, -50, 780, 1440, 900)
    expect(c.x).toBe(-780 + 90)
    expect(c.y).toBe(0)
  })
  it('shrinks width to the viewport', () => {
    expect(clampWindow(0, 0, 780, 400, 900).w).toBeLessThanOrEqual(400 - 16)
  })
})
