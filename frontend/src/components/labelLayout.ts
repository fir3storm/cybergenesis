/**
 * Deterministic screen-space-approximation for 3D node labels (F8c #5).
 *
 * Full per-frame camera projection was considered too risky to bolt onto the
 * demand/always frameloop without a regression harness for the 3D view, so
 * this implements the pragmatic approximation allowed by the spec: nodes that
 * share a zone are staggered vertically by their depth (z) order. Nodes
 * sorted front-to-back (ascending z, then x, then id for determinism) cycle
 * through three vertical tiers — 0, 0.42, 0.84 world units — so neighbouring
 * labels in the same zone never sit at exactly the same height and no label
 * drifts far from its node, regardless of the input array order. Labels are
 * never hidden; dimming is handled by the existing focus logic in TwinScene.
 */

export interface LabelAsset {
  id: string
  zone: string
  pos: [number, number, number]
}

/** Vertical step (world units) between staggered labels in one zone. */
export const LABEL_STEP = 0.42

export interface LabelPlacement {
  /** world-unit Y offset added to the label anchor */
  offset: number
  /** 0-based tier inside the zone (drives the Html zIndexRange) */
  tier: number
}

export function computeLabelOffsets(assets: readonly LabelAsset[]): Map<string, LabelPlacement> {
  const byZone = new Map<string, LabelAsset[]>()
  for (const a of assets) {
    const list = byZone.get(a.zone)
    if (list) list.push(a)
    else byZone.set(a.zone, [a])
  }
  const out = new Map<string, LabelPlacement>()
  for (const list of byZone.values()) {
    const sorted = [...list].sort((x, y) =>
      x.pos[2] - y.pos[2] || x.pos[0] - y.pos[0] || x.id.localeCompare(y.id))
    sorted.forEach((a, i) => {
      const tier = i % 3
      out.set(a.id, { offset: tier * LABEL_STEP, tier })
    })
  }
  return out
}
