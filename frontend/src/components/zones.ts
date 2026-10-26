/** Fixed, deterministic zone layout (left -> right). No random positions. */

export interface ZoneDef { id: string; label: string; x: number; color: string }

export const ZONES: ZoneDef[] = [
  { id: 'edge', label: 'INTERNET / EDGE', x: -8.2, color: '#38bdf8' },
  { id: 'dmz', label: 'DMZ', x: -4.6, color: '#22d3ee' },
  { id: 'app', label: 'APP TIER', x: -0.8, color: '#2dd4bf' },
  { id: 'data', label: 'DATA TIER', x: 3.2, color: '#34d399' },
  { id: 'endpoints', label: 'ENDPOINTS', x: 7.2, color: '#a78bfa' },
]

/** asset id -> [x, iconHeight, z] (iconHeight = pedestal top; sensor is elevated) */
export const NODE_LAYOUT: Record<string, [number, number, number]> = {
  internet: [-8.2, 1.0, -1.9],
  firewall: [-8.2, 1.0, 1.3],
  'web-server': [-4.6, 1.0, -0.4],
  'app-server': [-0.8, 1.0, -1.7],
  'identity-provider': [-0.8, 1.0, 1.7],
  database: [3.2, 1.0, -1.9],
  'file-server': [3.2, 1.0, 1.5],
  'admin-workstation': [7.2, 1.0, -1.7],
  'employee-workstation': [7.2, 1.0, 1.7],
  'security-sensor': [0.9, 2.9, 0.2],
}

export const ZONE_OF: Record<string, string> = {
  internet: 'edge', firewall: 'edge', 'web-server': 'dmz',
  'app-server': 'app', 'identity-provider': 'app',
  database: 'data', 'file-server': 'data',
  'admin-workstation': 'endpoints', 'employee-workstation': 'endpoints',
  'security-sensor': 'app',
}

export function layoutFor(id: string, fallback: [number, number, number]): [number, number, number] {
  return NODE_LAYOUT[id] ?? fallback
}
