/** The button under a long table that shows its next rows (rowLimit.ts), and how many of them are shown. */
import { fmt } from '../lib/format'
import { ROW_STEP } from './rowLimit'

export function ShowMore({ shown, total, more }: { shown: number; total: number; more: () => void }) {
  if (shown >= total) return null
  return (
    <p className="sub show-more">
      <button type="button" onClick={more}>
        Show {fmt(Math.min(ROW_STEP, total - shown), 0)} more
      </button>{' '}
      {fmt(shown, 0)} of {fmt(total, 0)} rows shown.
    </p>
  )
}
