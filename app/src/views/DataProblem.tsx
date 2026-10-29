import { EXPORT_COMMAND, describeLoadFailure } from '../data/loadAppData'

/** Shown where a page needs exported data that could not be loaded: the reason, and how to regenerate the files. */
export function DataProblem({ error }: { error: unknown }) {
  return (
    <div role="alert" className="data-problem">
      <p>{describeLoadFailure(error)}</p>
      <p>
        The app only draws files that the Python side exports. From the repository root run <code>{EXPORT_COMMAND}</code> to
        write them into <code>app/public/data/</code>, then reload this page.
      </p>
    </div>
  )
}
