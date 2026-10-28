import { X } from 'lucide-react'

/** Plain-language captions for each stage of the closed loop, keyed by run state. */
export const JUDGE_STEPS: { states: string[]; title: string; caption: string }[] = [
  { states: ['SCENARIO_SELECTED', 'ATTACK_SIMULATING'], title: 'Attack',
    caption: 'A typed ransomware playbook runs against a synthetic digital twin. No real systems, no payloads.' },
  { states: ['TELEMETRY_COLLECTED'], title: 'Observe',
    caption: 'The Observer turns raw telemetry into a structured observation with evidence references.' },
  { states: ['INVESTIGATING'], title: 'Reason',
    caption: 'The Investigator forms a hypothesis from the evidence. Its output is schema-validated, never executed.' },
  { states: ['DEFENSE_PROPOSED'], title: 'Propose + simulate',
    caption: 'The Strategist proposes defenses; each candidate is replayed on a cloned twin before anything is applied.' },
  { states: ['POLICY_VALIDATING', 'AWAITING_APPROVAL'], title: 'Guardrails',
    caption: 'A deterministic policy engine, independent of the AI, checks every action. Risky changes wait for a human (phone QR).' },
  { states: ['DEFENSE_APPLYING'], title: 'Act',
    caption: 'Only allowlisted actions run, through typed twin operations. The AI has no shell, filesystem or network access.' },
  { states: ['VERIFYING'], title: 'Verify',
    caption: 'The attack is replayed independently. PASS only if the target is provably unreachable; failures are shown as FAIL.' },
  { states: ['COMPLETED'], title: 'Prove',
    caption: 'Download the Ed25519-signed proof certificate, read the board briefing, or fork the run in the Time Machine.' },
]

export function judgeStepIndex(state: string): number {
  const i = JUDGE_STEPS.findIndex((s) => s.states.includes(state))
  return i < 0 ? 0 : i
}

export function JudgeCaptions({ state, outcome, onClose }: { state: string; outcome: string | undefined; onClose: () => void }) {
  const failed = state === 'FAILED'
  const idx = judgeStepIndex(state)
  const step = JUDGE_STEPS[idx]
  return (
    <div role="status" aria-live="polite" aria-label="Judge mode captions"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-violet-600 bg-slate-950/95 px-4 py-3 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-start gap-3">
        <span className="rounded bg-violet-600 px-2 py-0.5 text-[10px] font-black tracking-wider text-white">JUDGE MODE</span>
        <div className="min-w-0 flex-1">
          <ol className="flex flex-wrap gap-1 text-[10px]">
            {JUDGE_STEPS.map((s, i) => (
              <li key={s.title} className={`rounded px-1.5 py-0.5 ${i < idx ? 'bg-emerald-900 text-emerald-200' : i === idx ? 'bg-violet-700 font-bold text-white' : 'bg-slate-800 text-slate-400'}`}>
                {i + 1}. {s.title}
              </li>
            ))}
          </ol>
          <p className="mt-1 text-sm text-slate-100">
            {failed ? 'The run failed and is labelled FAILED with the reason. CYBERGENESIS never reports a fake success.'
              : state === 'COMPLETED' && outcome
                ? `${outcome === 'PASS' ? 'PASS: the fix was verified.' : 'FAIL: the defense did not close the path, and it says so.'} ${step.caption}`
                : step.caption}
          </p>
        </div>
        <button onClick={onClose} aria-label="Exit judge mode" className="rounded p-1 text-slate-400 hover:bg-slate-800"><X size={16} /></button>
      </div>
    </div>
  )
}
