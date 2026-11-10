/**
 * "Where these numbers come from" for an engine dataset: the run block of blotter.json or positions_timeline.json, as the
 * file gives it. Both files carry the same run, and both pages name it, so a reader can tell the two are one run.
 */
import type { Blotter, EngineRunBlock } from '../lib/contract'

/** The run block as a list of facts: what the provenance of a file with one run shows, and of each run of a file with several. */
export function RunMeta({ run, schemaVersion }: { run: EngineRunBlock; schemaVersion: string }) {
  return (
    <dl className="meta">
      <dt>Run</dt>
      <dd>
        <code>{run.run_id}</code>
      </dd>
      <dt>Strategy</dt>
      <dd>{run.strategy}</dd>
      <dt>Purpose</dt>
      <dd>{run.run_purpose}</dd>
      <dt>Split</dt>
      <dd>{run.split}</dd>
      <dt>Status</dt>
      <dd>{run.status}</dd>
      <dt>Data source</dt>
      <dd>{run.data_source}</dd>
      <dt>Execution</dt>
      <dd>
        {run.execution_mode}, fills at {run.fill_timing.replace('_', ' ')}, caps {run.cap_mode.replace('_', ' ')}, chain mask {run.chain_mask}
      </dd>
      <dt>Dates</dt>
      <dd>
        {run.sample_start} to {run.sample_end}
      </dd>
      <dt>Engine commit</dt>
      <dd>
        <code>{run.engine_commit}</code>
      </dd>
      <dt>Configuration</dt>
      <dd>
        <code>{run.config_hash}</code>
      </dd>
      <dt>Inputs</dt>
      <dd>
        <code>{run.data_fingerprint}</code>
      </dd>
      <dt>Schema version</dt>
      <dd>{schemaVersion}</dd>
    </dl>
  )
}

export function RunProvenance({ file }: { file: Pick<Blotter, 'run' | 'label' | 'schema_version'> }) {
  return (
    <>
      <h3>Where these numbers come from</h3>
      <p className="sub">{file.label}</p>
      <RunMeta run={file.run} schemaVersion={file.schema_version} />
    </>
  )
}
