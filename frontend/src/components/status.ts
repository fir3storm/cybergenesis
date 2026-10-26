export const ATTACK_PATHS: Record<string, string[]> = {
  ransomware_activity: ['employee-workstation', 'file-server'],
  compromised_identity: ['admin-workstation', 'database'],
  lateral_movement: ['internet', 'firewall', 'web-server', 'app-server', 'database'],
  data_exfiltration: ['database', 'app-server', 'web-server', 'firewall', 'internet'],
}

export const STATUS_COLOR: Record<string, string> = {
  healthy: '#22d3ee', exposed: '#f59e0b', suspicious: '#fb923c',
  compromised: '#ef4444', contained: '#38bdf8', recovering: '#a78bfa', remediated: '#34d399',
}
