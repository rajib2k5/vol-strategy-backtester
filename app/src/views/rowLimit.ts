/**
 * How many rows of a long table are shown: a ten-year run has thousands of fills, and drawing them all at once would
 * make the page slow for rows nobody scrolls to. ShowMore.tsx draws the button that asks for the next ones; the caller
 * keys its table on whatever filters it, so a new filter starts again from the first rows.
 */
import { useState } from 'react'

/** Rows shown at first, and added by each press. */
export const ROW_STEP = 250

export function useRowLimit(): [number, () => void] {
  const [limit, setLimit] = useState(ROW_STEP)
  return [limit, () => setLimit((n) => n + ROW_STEP)]
}
