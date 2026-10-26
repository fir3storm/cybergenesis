export interface Asset {
  id: string; name: string; asset_type: string; zone: string; posture: number;
  status: string; isolated: boolean; service_disabled: boolean;
  vulnerabilities: string[]; connected: string[]; pos: [number, number, number];
}
export interface Conn { source: string; target: string; trust: string; traversable: boolean; types: string[]; active: boolean }
export interface Twin { assets: Asset[]; connections: Conn[]; identities: Record<string, { asset: string; session_active: boolean; compromised: boolean; credential_version: number }>; containment: string[] }
export interface Scenario { id: string; name: string; description: string; severity: string; source_asset: string; target_asset: string; invariant: string; objectives: string[] }
export interface SimEvent { event_type: string; run_id?: string; agent?: string | null; asset_id?: string | null; message: string; payload?: Record<string, unknown>; seq?: number; timestamp?: string; twin?: Twin }
export interface RunResult {
  run: { id: string; scenario_id: string; seed: number; state: string; mode: string; error: string | null; metrics: Record<string, unknown> };
  usage?: { prompt_tokens: number; completion_tokens: number; calls: number; models: string[] };
  verification: { outcome: string; invariant: string; checks: { name: string; passed: boolean; detail: string }[]; metrics: Record<string, unknown> } | null;
  decisions: { agent: string; decision: string; justification: string; confidence: number; model: string; mode: string; asset_ids: string[] }[];
  policy: { action_type: string; asset_id: string; approved: boolean; reasons: string[] }[];
  executions: { action_type: string; asset_id: string; success: boolean; transition: Record<string, unknown> }[];
}
export interface ModelStatus { configured: boolean; reachable: boolean; model: string; mode: string; detail: string }
export type View = 'welcome' | 'twin' | 'experiment' | 'agents' | 'attackpath' | 'verification' | 'evidence' | 'settings' | 'designer' | 'playbook' | 'library'

export interface LibraryItem { id: string; label: string; description: string; params_contract?: string; default_posture?: number; default_zone?: string }
export interface Library { asset_types: LibraryItem[]; attack_steps: LibraryItem[]; defense_actions: LibraryItem[]; verification_kinds: string[]; zones: string[] }
export interface CustomTwinDef { id: string; name: string; description: string; assets: { id: string; name: string; asset_type: string; zone: string; posture?: number; pos: number[]; vulnerabilities?: string[] }[]; connections: { source: string; target: string; trust?: string; traversable?: boolean; types?: string[] }[]; created_at: string }
export interface CustomScenarioDef { id: string; name: string; description: string; definition: Record<string, unknown>; created_at: string }
