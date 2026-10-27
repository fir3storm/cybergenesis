/**
 * Pure helpers for the device faceplate (F8c #3).
 *
 * Port count/layout comes from `twin.devices[].ports`, which the backend
 * builds from the catalog manifest (no truncation — see twin.py to_dict).
 * With up to 28 ports on a flagship switch the layout switches to a compact
 * multi-row grid instead of silently dropping ports.
 */

export type LinkState = 'up' | 'filtered' | 'down' | string

/** LED colour for a link state. Isolated assets are always down (red). */
export function ledColor(state: LinkState | undefined, isolated: boolean): string {
  if (isolated) return '#ef4444'
  if (!state) return '#475569'
  if (state === 'up') return '#22c55e'
  if (state === 'filtered') return '#f59e0b'
  return '#ef4444'
}

/**
 * Link for port index `i`: ports beyond the known links have no peer and
 * render dark — links are never cycled/reused across unrelated ports.
 */
export function linkStateForPort(
  links: readonly { peer: string; state: string }[],
  index: number,
  isolated: boolean,
): string | undefined {
  if (isolated) return 'down'
  return links[index]?.state
}

export interface FaceplateGrid {
  perRow: number
  rows: number
  /** horizontal pitch between port cells */
  step: number
  /** port jack width */
  boxW: number
  boxH: number
  rowH: number
  width: number
  height: number
}

/** Compact grid: ≤8 ports keep the roomy layout, larger counts wrap. */
export function faceplateGrid(count: number): FaceplateGrid {
  const n = Math.max(count, 1)
  const perRow = n <= 8 ? n : n <= 18 ? 9 : 14
  const rows = Math.ceil(n / perRow)
  const step = perRow > 10 ? 30 : perRow > 8 ? 36 : 44
  const boxW = step > 36 ? 32 : step > 30 ? 28 : 22
  const boxH = 26
  const rowH = 64
  return {
    perRow,
    rows,
    step,
    boxW,
    boxH,
    rowH,
    width: Math.max(perRow * step + 20, 220),
    height: rows * rowH + 12,
  }
}
