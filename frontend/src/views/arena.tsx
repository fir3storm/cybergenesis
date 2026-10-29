import { useEffect, useRef, useState } from 'react'
import { Play, RotateCcw, Swords, Trophy } from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../stores/store'
import type { ArenaEvaluation, ArenaLeague, ArenaMatch, ArenaMemorySummary } from '../types'
import { Twin2D } from './twin'

function saveJson(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click()
}

/** Arena: red vs blue on any scenario, AI picks among validated moves, score memory learns across matches. */
export function ArenaView() {
  const s = useStore()
  const [scenarioId, setScenarioId] = useState('red_vs_blue_battle')
  const [mode, setMode] = useState('ai')
  const [maxRounds, setMaxRounds] = useState(5)
  const [match, setMatch] = useState<ArenaMatch | null>(null)
  const [shown, setShown] = useState(0) // rounds revealed in the spectate replay
  const [league, setLeague] = useState<ArenaLeague | null>(null)
  const [memory, setMemory] = useState<ArenaMemorySummary | null>(null)
  const [past, setPast] = useState<{ id: string; scenario_id: string; winner: string; mode: string; rounds_played: number }[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const [evaluation, setEvaluation] = useState<ArenaEvaluation | null>(null)
  useEffect(() => { api.arenaEvaluation().then(setEvaluation).catch(() => undefined) }, [])
  const [trainingGames, setTrainingGames] = useState(5)
  const [training, setTraining] = useState(false)
  const [results, setResults] = useState<ArenaMatch[]>([])
  const stopTraining = useRef(false)
  useEffect(() => () => { stopTraining.current = true }, [])

  const train = async () => {
    stopTraining.current = false
    setTraining(true); setBusy(true); setErr(null); setResults([])
    try {
      for (let i = 0; i < trainingGames && !stopTraining.current; i++) {
        const next = await api.arenaPlay(scenarioId, mode, maxRounds)
        setResults(previous => [...previous, next])
        setMatch(next); setShown(next.rounds.length)
        if (next.memory) setMemory(next.memory)
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Training failed')
    } finally {
      setTraining(false); setBusy(false); refresh()
    }
  }

  const refresh = () => {
    api.arenaLeague().then(setLeague).catch(() => undefined)
    api.arenaMemory().then(setMemory).catch(() => undefined)
    api.arenaMatches().then(setPast).catch(() => undefined)
  }
  useEffect(refresh, [])
  useEffect(() => {
    if (!match || shown >= match.rounds.length) return
    const t = setTimeout(() => setShown((v) => v + 1), 900)
    return () => clearTimeout(t)
  }, [match, shown])

  const play = () => {
    setBusy(true); setErr(null)
    api.arenaPlay(scenarioId, mode, maxRounds)
      .then((m) => { setMatch(m); setShown(0); if (m.memory) setMemory(m.memory); refresh() })
      .catch((e: Error) => setErr(e.message))
      .finally(() => setBusy(false))
  }
  const openPast = (id: string) => {
    api.arenaMatch(id).then((m) => { setMatch(m); setShown(m.rounds.length) }).catch((e: Error) => setErr(e.message))
  }
  const visible = match?.rounds.slice(0, shown) ?? []
  const done = match && shown >= match.rounds.length

  return (
    <main className="p-6">
      <h1 className="flex items-center gap-2 text-2xl font-black text-cyan-200"><Swords /> Arena — Red vs Blue</h1>
      <p className="mt-1 max-w-3xl text-sm text-slate-400">
        Red attacks and Blue defends the synthetic twin until someone wins: <b className="text-red-300">Red wins</b> when its selected route survives a defense, or exposure remains at the round limit; <b className="text-cyan-300">Blue wins</b> by leaving Red no validated path. Block one route and Red can reroute next round.
        AI chooses among validated moves. Each scenario has its own outcome memory, which informs future choices. Training updates strategy scores, not model weights.
      </p>

      <section className="mt-4 flex flex-wrap items-end gap-2" aria-label="Arena controls">
        <label className="text-xs text-slate-400">Scenario
          <select disabled={busy} value={scenarioId} onChange={(e) => setScenarioId(e.target.value)} className="mt-1 block rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100">
            {s.scenarios.map((sc) => <option key={sc.id} value={sc.id}>{sc.name}</option>)}
          </select></label>
        <label className="text-xs text-slate-400">Strategy
          <select disabled={busy} value={mode} onChange={(e) => setMode(e.target.value)} className="mt-1 block rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100">
            <option value="ai">AI + learning (Meta, validated)</option>
            <option value="learned">Learning only (score memory)</option>
            <option value="deterministic">Deterministic (no learning)</option>
          </select></label>
        <label className="text-xs text-slate-400">Max rounds
          <input type="number" min={1} max={10} disabled={busy} value={maxRounds} onChange={(e) => setMaxRounds(Number(e.target.value))} className="mt-1 block w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100" /></label>
        <button onClick={play} disabled={busy} className="flex items-center gap-1 rounded bg-red-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">
          <Play size={14} /> {busy ? 'Playing match…' : 'Play match'}
        </button>
        {match && <button onClick={() => setShown(0)} className="flex items-center gap-1 rounded border border-slate-600 px-3 py-2 text-xs"><RotateCcw size={13} /> Watch replay</button>}
      </section>
      <section className="mt-4 rounded-lg border border-violet-800/60 bg-slate-900/60 p-4" aria-label="Self-play training">
        <h2 className="font-bold text-violet-200">Self-play training</h2>
        <p className="mt-1 text-xs text-slate-400">Each battle starts with a fresh twin and uses lessons from earlier battles. Stop takes effect after the current match. AI mode may make multiple provider calls per battle.</p>
        <div className="mt-3 flex items-center gap-3">
          <label className="text-xs">Battles
            <select aria-label="Training battles" disabled={busy} value={trainingGames} onChange={e => setTrainingGames(Number(e.target.value))} className="ml-2 rounded bg-slate-800 p-2">
              {[3, 5, 10, 20].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button disabled={busy || mode === 'deterministic'} onClick={train} className="rounded bg-violet-600 px-3 py-2 text-sm font-bold disabled:opacity-40">Train teams</button>
          {training && <button onClick={() => { stopTraining.current = true }} className="rounded border border-slate-600 px-3 py-2 text-sm">Stop after match</button>}
        </div>
        {mode === 'deterministic' && <p className="mt-2 text-xs text-amber-200">Select AI or Learning only to train adaptive teams.</p>}
        {results.length > 0 && <div className="mt-3" role="status">
          <p className="text-sm">{results.length} / {trainingGames} battles completed ? Red {results.filter(r => r.winner === 'red').length} ? Blue {results.filter(r => r.winner === 'blue').length}</p>
          <div className="mt-2 flex flex-wrap gap-2">{results.map((r, i) => <button key={r.id} onClick={() => { setMatch(r); setShown(r.rounds.length) }} className={`rounded border px-3 py-2 text-xs ${r.winner === 'red' ? 'border-red-700 text-red-200' : 'border-cyan-700 text-cyan-200'}`}>#{i + 1} {r.winner.toUpperCase()} ? disruption {r.total_disrupted}</button>)}</div>
          <p className="mt-2 text-xs text-slate-400">Observed outcomes, not a benchmark of improvement. Repeated wins can indicate a solved scenario.</p>
        </div>}
      </section>
      {match?.context_memory && <p className="mt-3 text-xs text-violet-200">Current scenario experience: {match.context_memory.matches} battles ? {match.context_memory.red_learned} attack routes ? {match.context_memory.blue_learned} defenses. Choices favor historically successful options; Blue prioritizes verified blocking defenses.</p>}
      {err && <p className="mt-2 text-sm text-red-300">Arena failed: {err}</p>}

      {league && (
        <section className="mt-4 grid gap-3 md:grid-cols-4" aria-label="Arena league">
          {[['Matches', league.matches], ['Red wins', league.red_wins], ['Blue wins', league.blue_wins], ['Matches learned from', memory?.matches ?? 0]].map(([k, v]) => (
            <div key={k} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-center">
              <div className="text-[11px] text-slate-400">{k}</div><div className="text-2xl font-black text-cyan-200">{v}</div>
            </div>
          ))}
        </section>
      )}

      {match && (
        <section className="mt-4" aria-label="Arena match">
          {done ? (
            <div className={`rounded-lg border p-4 ${match.winner === 'red' ? 'border-red-800 bg-red-950/30' : 'border-cyan-800 bg-cyan-950/30'}`} role="status">
              <p className="flex items-center gap-2 text-xl font-black"><Trophy className={match.winner === 'red' ? 'text-red-300' : 'text-cyan-300'} />
                {match.winner === 'red' ? 'RED WINS' : 'BLUE WINS'} — {match.reason}</p>
              <p className="mt-1 text-xs text-slate-400">Rounds {match.rounds_played} · total legitimate paths disrupted {match.total_disrupted} · target reachable at end: {String(match.target_reachable_final)} · mode {match.mode}</p>
              <button onClick={() => api.arenaCertificate(match.id).then((c) => saveJson(`arena-certificate-${match.id}.json`, c)).catch((e: Error) => setErr(e.message))}
                className="mt-2 rounded bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white">Download winner proof</button>
              <span className="ml-2 font-mono text-[11px] text-slate-400">Verify locally: python scripts/verify_cert.py arena-certificate-{match.id}.json</span>
            </div>
          ) : (
            <p className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-300" role="status">
              Round {Math.min(shown + 1, match.rounds.length)} of {match.rounds.length} — spectating…
            </p>
          )}

          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <div className="rounded-lg border border-red-900/60 bg-slate-900/60 p-3" aria-label="Red rounds">
              <h2 className="text-xs font-bold tracking-wider text-red-300">RED — ATTACKS</h2>
              {visible.map((r) => (
                <p key={r.round} className="mt-2 text-xs text-slate-300">
                  <b>Round {r.round}:</b> {r.red_path ? r.red_path.join(' → ') : 'identity objective'} <span className="font-mono text-[10px] text-slate-500">({r.red_chosen_by ?? 'deterministic'})</span>
                  {' '}→ {(r.selected_path_blocked === undefined ? r.target_reachable_after : !r.selected_path_blocked) ? <span className="text-red-300">target REACHED</span> : <span className="text-cyan-300">{r.target_reachable_after ? 'route blocked; Red can reroute' : 'all routes blocked'}</span>}
                </p>
              ))}
              {!visible.length && <p className="mt-2 text-xs text-slate-500">First round incoming…</p>}
            </div>
            <div className="rounded-lg border border-cyan-900/60 bg-slate-900/60 p-3" aria-label="Blue rounds">
              <h2 className="text-xs font-bold tracking-wider text-cyan-300">BLUE — DEFENSES</h2>
              {visible.map((r) => (
                <p key={r.round} className="mt-2 text-xs text-slate-300">
                  <b>Round {r.round}:</b> {r.blue_candidate ?? 'no defense'} <span className="font-mono text-[10px] text-slate-500">({r.blue_chosen_by ?? 'deterministic'})</span>
                  {' '}· disrupted {r.disrupted ?? '—'}
                  {r.policy_rejections.length > 0 && <span className="text-amber-300"> · policy rejected: {r.policy_rejections.join('; ')}</span>}
                </p>
              ))}
              {!visible.length && <p className="mt-2 text-xs text-slate-500">First defense incoming…</p>}
            </div>
          </div>

          <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <h2 className="text-xs font-bold tracking-wider text-slate-300">{done ? 'FINAL TWIN' : 'TWIN AT THIS ROUND'}</h2>
            <Twin2D twin={visible[visible.length - 1]?.twin_after ?? match.initial_twin ?? match.final_twin} />
          </div>
        </section>
      )}

      {match?.decisions && <section className="mt-4 rounded-lg border border-slate-800 p-4" aria-label="Decision evidence">
        <h2 className="font-bold text-cyan-200">Decision evidence</h2>
        {match.decisions.filter(d => visible.some(r => r.evidence_ref && d.evidence_refs.includes(r.evidence_ref))).map((d, i) => <details key={i} className="mt-2 text-xs">
          <summary className="cursor-pointer">{d.agent_role} ? {d.mode} ? {d.model_id}</summary>
          <p className="mt-1 text-slate-300">{d.justification}</p>
          <p className="text-slate-500">Confidence {Math.round(d.confidence * 100)}% ? {d.evidence_refs.join(', ')} ? {d.timestamp}</p>
          {d.fallback_reason && <p className="text-amber-300">Fallback: {d.fallback_reason}</p>}
        </details>)}
      </section>}
      <section className="mt-4 rounded-lg border border-slate-800 p-4" aria-label="Paired evaluation">
        <h2 className="font-bold text-cyan-200">Held-out strategy evaluation</h2>
        {evaluation?.available && evaluation.summary ? <>
          <p className="mt-1 text-xs text-slate-400">Seed {evaluation.seed} · {evaluation.created_at} · {evaluation.live_requested ? 'AI requested; inspect live counts and provider failures below' : 'Offline evaluation; no live AI comparison'}</p>
          <div className="overflow-x-auto"><table className="mt-3 w-full text-left text-xs"><thead><tr>{['Strategy', 'Blue wins', 'Business paths disrupted', 'Edges removed', 'Edge gap', 'Mean ms', 'Tokens', 'Live cases', 'Provider failures', 'Fallbacks'].map(h => <th key={h} className="p-2">{h}</th>)}</tr></thead>
            <tbody>{Object.entries(evaluation.summary).map(([name, row]) => <tr key={name} className="border-t border-slate-800"><td className="p-2">{name}</td><td>{row.blue_wins}/{row.cases}</td><td>{row.mean_disrupted.toFixed(1)}</td><td>{row.mean_edges_removed?.toFixed(1) ?? '—'}</td><td>{row.mean_optimality_gap?.toFixed(1) ?? '—'}</td><td>{row.mean_latency_ms}</td><td>{row.tokens}</td><td>{row.live_cases}</td><td>{row.provider_failures ?? 0}</td><td>{row.fallbacks}</td></tr>)}</tbody></table></div>
          {!!evaluation.within_context?.length && <p className="mt-2 text-xs text-slate-400">Separate repeated-context check: {evaluation.within_context.length} training topologies replayed after one recorded match each; {evaluation.within_context.filter(row => row.warm_disrupted < row.cold_disrupted).length} reduced disruption. This does not measure generalization to unseen networks.</p>}
          <p className="mt-2 text-xs text-slate-500">{evaluation.limitations}</p>
        </> : <p className="mt-2 text-xs text-slate-400">No evaluation report available yet.</p>}
      </section>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-800 bg-slate-900/60 p-3" aria-label="What the arena learned">
          <h2 className="text-xs font-bold tracking-wider text-slate-300">WHAT THE ARENA LEARNED</h2>
          {!memory || memory.matches === 0 ? <p className="mt-1 text-xs text-slate-500">No matches yet — play one and both sides start learning.</p> : (
            <div className="mt-1 grid gap-2 text-xs md:grid-cols-2">
              <div><p className="text-cyan-300">Blue defenses (blocks / plays)</p>
                {Object.entries(memory.blue).slice(0, 6).map(([k, v]) => <p key={k} className="mt-0.5 text-slate-300">{k}: {v.blocks}/{v.plays}</p>)}</div>
              <div><p className="text-red-300">Red paths (reached / plays)</p>
                {Object.entries(memory.red).slice(0, 6).map(([k, v]) => <p key={k} className="mt-0.5 text-slate-300">{k}: {v.reaches}/{v.plays}</p>)}</div>
            </div>
          )}
        </section>
        <section className="rounded-lg border border-slate-800 bg-slate-900/60 p-3" aria-label="Past matches">
          <h2 className="text-xs font-bold tracking-wider text-slate-300">PAST MATCHES</h2>
          {past.length === 0 && <p className="mt-1 text-xs text-slate-500">None yet.</p>}
          {past.slice(0, 8).map((m) => (
            <button key={m.id} onClick={() => openPast(m.id)} className="mt-1 block w-full rounded border border-slate-800 px-2 py-1 text-left text-xs text-slate-300 hover:border-cyan-700">
              {m.scenario_id} — <b className={m.winner === 'red' ? 'text-red-300' : 'text-cyan-300'}>{m.winner.toUpperCase()}</b> in {m.rounds_played} round(s) · {m.mode}
            </button>
          ))}
          {league && league.by_scenario.length > 0 && (
            <p className="mt-2 text-[11px] text-slate-500">{league.by_scenario.map((t) => `${t.scenario_id}: R${t.red_wins}–B${t.blue_wins}`).join(' · ')}</p>
          )}
        </section>
      </div>
    </main>
  )
}
