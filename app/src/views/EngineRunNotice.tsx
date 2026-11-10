/**
 * The notice at the top of the Blotter and Positions pages: the run behind them is a diagnostic one that exercises the
 * engine, not a strategy result, and the files carry no P&L. Worded for the file's own run block (content/engineRun.ts);
 * `run` is null while there is no file.
 */
import type { EngineRunBlock } from '../lib/contract'
import { engineRunNotice } from '../content/engineRun'

export function EngineRunNotice({ run }: { run: EngineRunBlock | null }) {
  const { headline, body } = engineRunNotice(run)
  return (
    <section className="notice" aria-label="What this run is">
      <strong>{headline}</strong> {body}
    </section>
  )
}
