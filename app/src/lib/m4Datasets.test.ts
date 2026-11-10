/**
 * The contract of signals_timeline.json and strategy_positions.json (milestone 4, schema 0.5.0): the fixture of each parses,
 * then one thing at a time is changed and the parser must refuse it, naming the path and the problem of that one thing.
 * Every fixture value is made up.
 */
import { describe, expect, it } from 'vitest'
import {
  ContractError,
  ENGINE_RUN_KEYS,
  M4_DATASETS_MIN_VERSION,
  SIGNALS_TIMELINE_UNITS,
  SIGNAL_FLAG_NAMES,
  STRATEGY_POSITIONS_UNITS,
  STRATEGY_STRUCTURES,
  parseSignalsTimeline,
  parseStrategyPositions,
} from './contract'
import signalsFixture from '../test/fixtures/signals_timeline.json'
import strategiesFixture from '../test/fixtures/strategy_positions.json'

type Obj = Record<string, unknown>
type SigDoc = Obj & {
  run: Obj
  units: Obj
  signal: Obj
  thresholds: Obj
  dates: unknown[]
  iv30: unknown[]
  rv_forecast: unknown[]
  rv_realised: unknown[]
  log_var_ratio: unknown[]
  model_fit_date: unknown[]
  n_window: unknown[]
  flags: unknown[]
  flag_names: unknown[]
  fits: Obj[]
  forecast_test: (Obj & { ci: unknown[] }) | null
}
type Pos = Obj & { legs: Obj[] }
type StratDoc = Obj & { units: Obj; runs: (Obj & { run: Obj; params: unknown; positions: Pos[] })[] }

const copySig = (): SigDoc => JSON.parse(JSON.stringify(signalsFixture)) as SigDoc
const copyStrat = (): StratDoc => JSON.parse(JSON.stringify(strategiesFixture)) as StratDoc

/** Assert parse(raw) throws a ContractError whose message contains `fragment`. */
function rejects(parse: (raw: unknown) => unknown, raw: unknown, fragment: string): void {
  let err: unknown
  try {
    parse(raw)
  } catch (e) {
    err = e
  }
  expect(err, `expected a ContractError containing "${fragment}"`).toBeInstanceOf(ContractError)
  expect((err as Error).message).toContain(fragment)
}

const sig = (change: (d: SigDoc) => void): SigDoc => {
  const d = copySig()
  change(d)
  return d
}
const strat = (change: (d: StratDoc) => void): StratDoc => {
  const d = copyStrat()
  change(d)
  return d
}
const rejectsS = (change: (d: SigDoc) => void, fragment: string): void => rejects(parseSignalsTimeline, sig(change), fragment)
const rejectsT = (change: (d: StratDoc) => void, fragment: string): void => rejects(parseStrategyPositions, strat(change), fragment)

/** The fixture made the naive model: no fits, no fit date, no forecast test. */
function toNaive(d: SigDoc): void {
  d.signal.rv_model = 'naive'
  d.fits = []
  d.model_fit_date = d.dates.map(() => null)
  d.forecast_test = null
}

const OSI = (ymd: string, cp: 'C' | 'P', strike: number): string => `SPY   ${ymd}${cp}${String(strike * 1000).padStart(8, '0')}`

// ---------------------------------------------------------------- the fixtures parse

describe('signals_timeline: the fixture', () => {
  it('parses to the file it holds', () => {
    const f = parseSignalsTimeline(copySig())
    expect(f.dates).toHaveLength(60)
    expect(f.dates[0]).toBe('2019-10-01')
    expect(f.run.split).toBe('development')
    expect(f.signal).toEqual({ name: 'log_variance_ratio_demo', rv_model: 'har', window_days: 30, horizon: 21, min_pairs: 504 })
    expect(f.thresholds).toEqual({ short_entry: [0, 0.4], long_entry: 0, exit_band: 0.4 })
    expect(f.fits.map((x) => x.fit_date)).toEqual(['2019-09-30', '2019-10-31', '2019-11-29'])
    expect(f.iv30[20]).toBeNull()
    expect(f.log_var_ratio[20]).toBeNull()
    expect(f.rv_realised[f.rv_realised.length - 1]).toBeNull()
    expect(f.forecast_test?.decision).toBe('har')
    expect(f.flag_names).toEqual([...SIGNAL_FLAG_NAMES])
    expect(f.units).toEqual(SIGNALS_TIMELINE_UNITS)
  })
  it('parses the naive model with no fits and no forecast test', () => {
    const f = parseSignalsTimeline(sig(toNaive))
    expect(f.fits).toEqual([])
    expect(f.forecast_test).toBeNull()
    expect(f.model_fit_date.every((x) => x === null)).toBe(true)
  })
  it('parses a naive model that a forecast test chose', () => {
    const f = parseSignalsTimeline(
      sig((d) => {
        toNaive(d)
        d.forecast_test = { ...(copySig().forecast_test as Obj), p: 0.2, p_holm: 0.2, decision: 'naive', ci: [-0.001, 0.004] }
      }),
    )
    expect(f.forecast_test?.decision).toBe('naive')
  })
  it('ignores a key the file does not need', () => {
    expect(parseSignalsTimeline(sig((d) => void (d.extra = 1))).dates).toHaveLength(60)
  })
})

describe('strategy_positions: the fixture', () => {
  it('parses to the file it holds', () => {
    const f = parseStrategyPositions(copyStrat())
    expect(f.banner).toBe('7 development trials (made up); no performance before M6')
    expect(f.runs.map((r) => r.strategy)).toEqual(['ShortVolOnSignal', 'LongVolOnSignal'])
    expect(f.runs[0].positions.map((p) => p.structure)).toEqual(['short_straddle', 'short_strangle', 'straddle_calendar', 'short_straddle'])
    expect(new Set(f.runs.flatMap((r) => r.positions.map((p) => p.structure)))).toEqual(new Set(STRATEGY_STRUCTURES))
    expect(f.runs[0].positions[3]).toMatchObject({ closed: null, exit_reason: null })
    expect(f.runs[0].positions[2].entry_signal).toBeNull()
    expect(f.runs[0].params).toEqual({ entry_theta: 0.4, max_open: 1, note: 'made up' })
    expect(f.runs[1].n_trials_group).toBe(3)
    expect(f.units).toEqual(STRATEGY_POSITIONS_UNITS)
  })
  it('accepts an empty position list, and ignores a key the file does not need', () => {
    const f = parseStrategyPositions(
      strat((d) => {
        d.runs[1].positions = []
        d.extra = 1
      }),
    )
    expect(f.runs[1].positions).toEqual([])
  })
})

// ---------------------------------------------------------------- the envelope, the units and the label of both

describe('both datasets: the envelope', () => {
  const BOTH = [
    ['signals_timeline', parseSignalsTimeline, copySig] as const,
    ['strategy_positions', parseStrategyPositions, copyStrat] as const,
  ]
  it.each(BOTH)('%s: a file older than 0.5.0 is refused, 0.5.0 is not', (name, parse, copy) => {
    const old = { ...copy(), schema_version: '0.4.0' }
    rejects(parse, old, `${name}.schema_version: "0.4.0" is older than ${M4_DATASETS_MIN_VERSION}`)
    expect(() => parse({ ...copy(), schema_version: '0.5.0' })).not.toThrow()
    expect(() => parse({ ...copy(), schema_version: '0.10.0' })).not.toThrow()
  })
  it.each(BOTH)('%s: an illustrative file is refused', (name, parse, copy) => {
    rejects(parse, { ...copy(), illustrative: true }, `${name}.illustrative: must be false`)
  })
  it.each(BOTH)('%s: an empty label is refused', (name, parse, copy) => {
    rejects(parse, { ...copy(), label: ' ' }, `${name}.label: expected a non-empty string`)
  })
  it.each(BOTH)('%s: a unit other than the exporter\'s is refused', (name, parse, copy) => {
    const d = copy()
    ;(d.units as Obj)[name === 'signals_timeline' ? 'n_window' : 'ratio'] = 'a count'
    rejects(parse, d, `${name}.units.${name === 'signals_timeline' ? 'n_window' : 'ratio'}: "a count" is not the exporter's unit`)
  })
  it.each(BOTH)('%s: a missing top-level key is refused, by name', (name, parse, copy) => {
    const d = copy() as Obj
    delete d.generated_at
    rejects(parse, d, `${name}: missing required key "generated_at"`)
  })
})

// ---------------------------------------------------------------- the development split (decision D19)

describe('the development split: nothing after 2019 is shown', () => {
  it('signals_timeline: a run of another split is refused', () => {
    rejectsS((d) => (d.run.split = 'validation'), 'signals_timeline.run.split: is "validation" but this file shows the development split only')
  })
  it('signals_timeline: a sample that ends after 2019-12-31 is refused', () => {
    rejectsS((d) => (d.run.sample_end = '2020-01-31'), 'signals_timeline.run.sample_end: 2020-01-31 is after 2019-12-31')
  })
  it('signals_timeline: a sample that ends on 2019-12-31 is accepted', () => {
    expect(() => parseSignalsTimeline(sig((d) => (d.run.sample_end = '2019-12-31')))).not.toThrow()
  })
  it('signals_timeline: a date after 2019-12-31 is refused', () => {
    rejectsS((d) => (d.dates[59] = '2020-01-06'), `signals_timeline.dates[59]: 2020-01-06 is outside the run's sample 2019-10-01 to 2019-12-31`)
  })
  it('strategy_positions: a run of another split is refused', () => {
    rejectsT((d) => (d.runs[1].run.split = 'holdout'), 'strategy_positions.runs[1].run.split: is "holdout" but this file shows the development split only')
  })
  it('strategy_positions: a run whose sample ends after 2019-12-31 is refused', () => {
    rejectsT((d) => (d.runs[0].run.sample_end = '2020-01-02'), 'strategy_positions.runs[0].run.sample_end: 2020-01-02 is after 2019-12-31')
  })
  it('strategy_positions: a run with a missing run key is refused, by name', () => {
    rejectsT((d) => delete d.runs[0].run[ENGINE_RUN_KEYS[3]], 'strategy_positions.runs[0].run: missing required key "engine_commit"')
  })
})

// ---------------------------------------------------------------- signals_timeline

describe('signals_timeline: the signal block and the thresholds', () => {
  const CASES: [string, (d: SigDoc) => void, string][] = [
    ['an rv_model other than har or naive', (d) => (d.signal.rv_model = 'ols'), 'signals_timeline.signal.rv_model: expected one of "har", "naive"'],
    ['an empty signal name', (d) => (d.signal.name = ''), 'signals_timeline.signal.name: expected a non-empty string'],
    ['a window_days other than 30', (d) => (d.signal.window_days = 31), 'signals_timeline.signal.window_days: expected 30, got 31'],
    ['a horizon other than 21', (d) => (d.signal.horizon = 20), 'signals_timeline.signal.horizon: expected 21, got 20'],
    ['a min_pairs other than 504', (d) => (d.signal.min_pairs = 500), 'signals_timeline.signal.min_pairs: expected 504, got 500'],
    ['a short_entry other than [0, 0.4]', (d) => (d.thresholds.short_entry = [0, 0.5]), 'signals_timeline.thresholds.short_entry: expected [0, 0.4], got [0,0.5]'],
    ['a short_entry of the wrong length', (d) => (d.thresholds.short_entry = [0]), 'signals_timeline.thresholds.short_entry: expected [0, 0.4], got [0]'],
    ['a long_entry other than 0', (d) => (d.thresholds.long_entry = 0.1), 'signals_timeline.thresholds.long_entry: expected 0, got 0.1'],
    ['an exit_band other than 0.4', (d) => (d.thresholds.exit_band = 0.5), 'signals_timeline.thresholds.exit_band: expected 0.4, got 0.5'],
  ]
  it.each(CASES)('refuses %s', (_name, change, fragment) => rejectsS(change, fragment))
})

describe('signals_timeline: the dates and the series', () => {
  const CASES: [string, (d: SigDoc) => void, string][] = [
    ['no dates', (d) => (d.dates = []), 'signals_timeline.dates: needs at least 1 date'],
    ['a date that does not exist', (d) => (d.dates[3] = '2019-10-32'), 'signals_timeline.dates[3]: "2019-10-32" is not a calendar date'],
    ['a date before the run\'s sample', (d) => (d.run.sample_start = '2019-10-02'), `signals_timeline.dates[0]: 2019-10-01 is outside the run's sample 2019-10-02`],
    ['dates that do not increase', (d) => (d.dates[5] = d.dates[4]), 'signals_timeline.dates[5]: must be strictly increasing'],
    ['an iv30 series of the wrong length', (d) => d.iv30.pop(), 'signals_timeline.iv30: has 59 values but dates has 60'],
    ['an rv_forecast series of the wrong length', (d) => d.rv_forecast.push(0.1), 'signals_timeline.rv_forecast: has 61 values but dates has 60'],
    ['an rv_realised series of the wrong length', (d) => d.rv_realised.pop(), 'signals_timeline.rv_realised: has 59 values but dates has 60'],
    ['a log_var_ratio series of the wrong length', (d) => d.log_var_ratio.pop(), 'signals_timeline.log_var_ratio: has 59 values but dates has 60'],
    ['an iv30 of 0', (d) => (d.iv30[4] = 0), 'signals_timeline.iv30[4]: expected a number above 0 or null, got 0'],
    ['a negative rv_forecast', (d) => (d.rv_forecast[7] = -0.1), 'signals_timeline.rv_forecast[7]: expected a number above 0 or null, got -0.1'],
    ['an rv_realised of 0', (d) => (d.rv_realised[2] = 0), 'signals_timeline.rv_realised[2]: expected a number above 0 or null, got 0'],
    ['a string among the numbers', (d) => (d.iv30[4] = '0.15'), 'signals_timeline.iv30[4]: expected a finite number, got 0.15'],
    ['a log_var_ratio that is not finite', (d) => (d.log_var_ratio[5] = 'x'), 'signals_timeline.log_var_ratio[5]: expected a finite number'],
    ['a log_var_ratio with iv30 null', (d) => (d.log_var_ratio[20] = 0.1), 'signals_timeline.log_var_ratio[20]: is 0.1 but iv30[20] is null'],
    [
      'a log_var_ratio with rv_forecast null',
      (d) => (d.log_var_ratio[0] = 0.2),
      'signals_timeline.log_var_ratio[0]: is 0.2 but rv_forecast[0] is null',
    ],
    [
      'an rv_realised in a window that ends after 2019',
      (d) => (d.rv_realised[d.dates.indexOf('2019-12-02')] = 0.15),
      'signals_timeline.rv_realised[44]: is 0.15 but the 30-day window from 2019-12-02 ends after 2019-12-31',
    ],
  ]
  it.each(CASES)('refuses %s', (_name, change, fragment) => rejectsS(change, fragment))

  it('accepts a negative log_var_ratio, and a realised vol whose window ends exactly on 2019-12-31', () => {
    const f = parseSignalsTimeline(
      sig((d) => {
        const at = d.dates.indexOf('2019-11-29')
        d.dates[at] = '2019-12-01'
        d.rv_realised[at] = 0.15
        d.log_var_ratio[10] = -0.7
      }),
    )
    expect(f.log_var_ratio[10]).toBe(-0.7)
    expect(f.rv_realised[f.dates.indexOf('2019-12-01')]).toBe(0.15)
  })
})

describe('signals_timeline: the fits and the model each date used', () => {
  const CASES: [string, (d: SigDoc) => void, string][] = [
    ['a fit after 2019-12-31', (d) => (d.fits[2].fit_date = '2020-01-03'), 'signals_timeline.fits[2].fit_date: 2020-01-03 is after 2019-12-31'],
    ['fits that do not increase', (d) => (d.fits[1].fit_date = d.fits[0].fit_date), 'signals_timeline.fits[1].fit_date: must be strictly increasing'],
    ['a fit with 3 coefficients', (d) => d.fits[0].coef = [0.1, 0.2, 0.3], 'signals_timeline.fits[0].coef: expected 4 coefficients'],
    ['a fit coefficient that is not a number', (d) => ((d.fits[1].coef as unknown[])[2] = 'a'), 'signals_timeline.fits[1].coef[2]: expected a finite number'],
    ['a fit of 503 pairs', (d) => (d.fits[1].n_pairs = 503), 'signals_timeline.fits[1].n_pairs: expected a whole number of at least 504, got 503'],
    ['a fit_date that does not exist', (d) => (d.fits[0].fit_date = '2019-02-30'), 'signals_timeline.fits[0].fit_date: "2019-02-30" is not a calendar date'],
    ['a model_fit_date series of the wrong length', (d) => d.model_fit_date.pop(), 'signals_timeline.model_fit_date: has 59 values but dates has 60'],
    ['a model_fit_date that is not a date', (d) => (d.model_fit_date[5] = 20191031), 'signals_timeline.model_fit_date[5]: 20191031 is not a calendar date'],
    ['a model_fit_date after its date', (d) => (d.model_fit_date[2] = '2019-11-29'), 'signals_timeline.model_fit_date[2]: 2019-11-29 is after the date 2019-10-03'],
    ['a model_fit_date that is no fit', (d) => (d.model_fit_date[2] = '2019-10-02'), 'signals_timeline.model_fit_date[2]: 2019-10-02 is not the fit_date of any entry of fits'],
    [
      'fits for the naive model',
      (d) => {
        toNaive(d)
        d.fits = (copySig().fits)
      },
      'signals_timeline.fits: must be empty for the naive model',
    ],
    [
      'a model_fit_date for the naive model',
      (d) => {
        toNaive(d)
        d.model_fit_date[7] = '2019-09-30'
      },
      'signals_timeline.model_fit_date[7]: is 2019-09-30 but the naive model has no fit',
    ],
  ]
  it.each(CASES)('refuses %s', (_name, change, fragment) => rejectsS(change, fragment))
})

describe('signals_timeline: n_window, flags and flag_names', () => {
  const CASES: [string, (d: SigDoc) => void, string][] = [
    ['a negative n_window', (d) => (d.n_window[3] = -1), 'signals_timeline.n_window[3]: expected a whole number of at least 0, got -1'],
    ['an n_window of the wrong length', (d) => d.n_window.pop(), 'signals_timeline.n_window: has 59 values but dates has 60'],
    ['a flags value of 16', (d) => (d.flags[4] = 16), 'signals_timeline.flags[4]: 16 is above 15'],
    ['a flags value that is not whole', (d) => (d.flags[4] = 1.5), 'signals_timeline.flags[4]: expected a whole number of at least 0, got 1.5'],
    ['a flags series of the wrong length', (d) => d.flags.pop(), 'signals_timeline.flags: has 59 values but dates has 60'],
    ['flag_names in another order', (d) => d.flag_names.reverse(), 'signals_timeline.flag_names: expected [RV_FALLBACK, RV_MISSING, IV30_MISSING, WINDOW_EMPTY]'],
    ['too few flag_names', (d) => d.flag_names.pop(), 'signals_timeline.flag_names: expected [RV_FALLBACK'],
  ]
  it.each(CASES)('refuses %s', (_name, change, fragment) => rejectsS(change, fragment))

  it('accepts a flags value of 15, the value with every bit set', () => {
    expect(parseSignalsTimeline(sig((d) => (d.flags[4] = 15))).flags[4]).toBe(15)
  })
})

describe('signals_timeline: the forecast test', () => {
  it('carries the threshold and the effective size through', () => {
    const f = parseSignalsTimeline(copySig()).forecast_test
    expect(f?.threshold).toBe(0.025)
    expect(f?.effective_size.worst_matched_battery_seed).toEqual({ rate: 0.0815, null_side: 'S4 f=0.15 right +d (made up)' })
    expect(f?.effective_size.abc_size_second_seed).toBe(0.0502)
    expect(f?.effective_size.threshold).toBe(0.025)
    expect(f?.p_holm).toBe(f?.p)
    expect(f?.fragile_band).toEqual([0.02, 0.05])
    expect(f?.fragile).toBe(false)
  })
  it('accepts a fragile result: p 0.022 inside the band, decided har', () => {
    const f = parseSignalsTimeline(
      sig((d) => {
        ft(d, 'p', 0.022)
        ft(d, 'p_holm', 0.022)
        ft(d, 'fragile', true)
      }),
    ).forecast_test
    expect(f).toMatchObject({ p: 0.022, p_holm: 0.022, decision: 'har', fragile: true, fragile_band: [0.02, 0.05] })
  })
  it('takes the band as half-open: fragile at p = lo, not at p = hi', () => {
    const lo = sig((d) => {
      ft(d, 'p', 0.02)
      ft(d, 'p_holm', 0.02)
      ft(d, 'fragile', true)
    })
    expect(parseSignalsTimeline(lo).forecast_test?.fragile).toBe(true)
    const hi = sig((d) => {
      toNaive(d)
      d.forecast_test = { ...(copySig().forecast_test as Obj), p: 0.05, p_holm: 0.05, decision: 'naive', fragile: false, ci: [0.0007, 0.0077] }
    })
    expect(parseSignalsTimeline(hi).forecast_test?.fragile).toBe(false)
  })
  const ft = (d: SigDoc, key: string, value: unknown): void => void ((d.forecast_test as Obj)[key] = value)
  const es = (d: SigDoc): Obj => (d.forecast_test as Obj).effective_size as Obj
  const CASES: [string, (d: SigDoc) => void, string][] = [
    ['an empty prereg_id', (d) => ft(d, 'prereg_id', ''), 'signals_timeline.forecast_test.prereg_id: expected a non-empty string'],
    ['an upper-case prereg_sha256', (d) => ft(d, 'prereg_sha256', 'F'.repeat(64)), 'signals_timeline.forecast_test.prereg_sha256: "FFFF'],
    ['a k other than 1', (d) => ft(d, 'k', 2), 'signals_timeline.forecast_test.k: expected 1, got 2'],
    ['an n of 0', (d) => ft(d, 'n', 0), 'signals_timeline.forecast_test.n: expected a whole number of at least 1, got 0'],
    ['a q of 0', (d) => ft(d, 'q', 0), 'signals_timeline.forecast_test.q: expected a whole number of at least 1, got 0'],
    ['a block of 0', (d) => ft(d, 'block', 0), 'signals_timeline.forecast_test.block: expected a whole number of at least 1, got 0'],
    ['draws of 0', (d) => ft(d, 'draws', 0), 'signals_timeline.forecast_test.draws: expected a whole number of at least 1, got 0'],
    ['an empty window', (d) => ft(d, 'window', ''), 'signals_timeline.forecast_test.window: expected a non-empty string'],
    ['an mean_d that is not a number', (d) => ft(d, 'mean_d', 'x'), 'signals_timeline.forecast_test.mean_d: expected a finite number'],
    ['an ewc_t that is not a number', (d) => ft(d, 'ewc_t', null), 'signals_timeline.forecast_test.ewc_t: expected a finite number'],
    ['a negative se', (d) => ft(d, 'se', -0.1), 'signals_timeline.forecast_test.se: expected a number of at least 0, got -0.1'],
    ['a p of 0', (d) => ft(d, 'p', 0), 'signals_timeline.forecast_test.p: 0 is outside (0, 1]'],
    ['a p_holm above 1', (d) => ft(d, 'p_holm', 1.2), 'signals_timeline.forecast_test.p_holm: 1.2 is outside (0, 1]'],
    ['a ci of one value', (d) => ft(d, 'ci', [0.1]), 'signals_timeline.forecast_test.ci: expected [lo, hi], got 1 value(s)'],
    ['a ci with lo above hi', (d) => ft(d, 'ci', [0.2, 0.1]), 'signals_timeline.forecast_test.ci: lo 0.2 is above hi 0.1'],
    ['a ci bound that is not a number', (d) => ft(d, 'ci', [0.1, 'x']), 'signals_timeline.forecast_test.ci[1]: expected a finite number'],
    ['an alpha of 0', (d) => ft(d, 'alpha', 0), 'signals_timeline.forecast_test.alpha: 0 is outside (0, 1)'],
    ['an alpha of 1', (d) => ft(d, 'alpha', 1), 'signals_timeline.forecast_test.alpha: 1 is outside (0, 1)'],
    ['a threshold of 0', (d) => ft(d, 'threshold', 0), 'signals_timeline.forecast_test.threshold: 0 is outside (0, 1)'],
    ['a threshold of 1', (d) => ft(d, 'threshold', 1), 'signals_timeline.forecast_test.threshold: 1 is outside (0, 1)'],
    ['a boolean threshold', (d) => ft(d, 'threshold', true), 'signals_timeline.forecast_test.threshold: expected a finite number, got true'],
    ['a boolean alpha', (d) => ft(d, 'alpha', true), 'signals_timeline.forecast_test.alpha: expected a finite number, got true'],
    ['a string threshold', (d) => ft(d, 'threshold', '0.025'), 'signals_timeline.forecast_test.threshold: expected a finite number, got 0.025'],
    ['a threshold that differs from alpha', (d) => ft(d, 'threshold', 0.05), 'signals_timeline.forecast_test.threshold: 0.05 differs from alpha 0.025'],
    ['no threshold', (d) => delete (d.forecast_test as Obj).threshold, 'signals_timeline.forecast_test: missing required key "threshold"'],
    ['no effective_size', (d) => delete (d.forecast_test as Obj).effective_size, 'signals_timeline.forecast_test: missing required key "effective_size"'],
    ['an effective_size that is not an object', (d) => ft(d, 'effective_size', 0.05), 'signals_timeline.forecast_test.effective_size: expected an object'],
    ['no abc_size_second_seed', (d) => delete es(d).abc_size_second_seed, 'signals_timeline.forecast_test.effective_size: missing required key "abc_size_second_seed"'],
    ['no effective_size.threshold', (d) => delete es(d).threshold, 'signals_timeline.forecast_test.effective_size: missing required key "threshold"'],
    ['an effective_size.threshold of 0', (d) => (es(d).threshold = 0), 'signals_timeline.forecast_test.effective_size.threshold: 0 is outside (0, 1)'],
    ['an effective_size.threshold that differs from the threshold', (d) => (es(d).threshold = 0.05), 'signals_timeline.forecast_test.effective_size.threshold: 0.05 differs from threshold 0.025'],
    ['an abc_size_battery_seed above the worst matched size of its seed', (d) => (es(d).abc_size_battery_seed = 0.0816), 'signals_timeline.forecast_test.effective_size.abc_size_battery_seed: 0.0816 is above the worst matched size 0.0815 of its seed'],
    ['an abc_size_second_seed above the worst matched size of its seed', (d) => (es(d).abc_size_second_seed = 0.084), 'signals_timeline.forecast_test.effective_size.abc_size_second_seed: 0.084 is above the worst matched size 0.083 of its seed'],
    ['a p_holm that differs from p (k = 1)', (d) => ft(d, 'p_holm', 0.024), 'signals_timeline.forecast_test.p_holm: 0.024 differs from p 0.012'],
    ['a worst_simulated_size below the worst matched battery-seed size', (d) => ft(d, 'worst_simulated_size', 0.08), 'signals_timeline.forecast_test.worst_simulated_size: 0.08 is below the worst matched battery-seed size 0.0815'],
    ['no fragile_band', (d) => delete (d.forecast_test as Obj).fragile_band, 'signals_timeline.forecast_test: missing required key "fragile_band"'],
    ['a fragile_band of one value', (d) => ft(d, 'fragile_band', [0.02]), 'signals_timeline.forecast_test.fragile_band: expected [lo, hi], got [0.02]'],
    ['a fragile_band that is not an array', (d) => ft(d, 'fragile_band', 0.05), 'signals_timeline.forecast_test.fragile_band: expected [lo, hi], got 0.05'],
    ['a fragile_band with lo at hi', (d) => ft(d, 'fragile_band', [0.03, 0.03]), 'signals_timeline.forecast_test.fragile_band: lo 0.03 is not below hi 0.03'],
    ['a fragile_band with lo above hi', (d) => ft(d, 'fragile_band', [0.05, 0.02]), 'signals_timeline.forecast_test.fragile_band: lo 0.05 is not below hi 0.02'],
    ['a fragile_band with a boolean edge', (d) => ft(d, 'fragile_band', [true, 0.05]), 'signals_timeline.forecast_test.fragile_band[0]: expected a finite number, got true'],
    ['a fragile_band with an edge of 0', (d) => ft(d, 'fragile_band', [0, 0.05]), 'signals_timeline.forecast_test.fragile_band[0]: 0 is outside (0, 1)'],
    ['a fragile_band with an edge of 1', (d) => ft(d, 'fragile_band', [0.02, 1]), 'signals_timeline.forecast_test.fragile_band[1]: 1 is outside (0, 1)'],
    ['no fragile', (d) => delete (d.forecast_test as Obj).fragile, 'signals_timeline.forecast_test: missing required key "fragile"'],
    ['a fragile of 0 (not a boolean)', (d) => ft(d, 'fragile', 0), 'signals_timeline.forecast_test.fragile: expected true or false, got 0'],
    ['a fragile of "false" (not a boolean)', (d) => ft(d, 'fragile', 'false'), 'signals_timeline.forecast_test.fragile: expected true or false, got false'],
    ['a fragile true with p below the band', (d) => ft(d, 'fragile', true), 'signals_timeline.forecast_test.fragile: is true but p 0.012 against the band [0.02, 0.05) makes it false'],
    [
      'a fragile false with p inside the band',
      (d) => {
        ft(d, 'p', 0.022)
        ft(d, 'p_holm', 0.022)
      },
      'signals_timeline.forecast_test.fragile: is false but p 0.022 against the band [0.02, 0.05) makes it true',
    ],
    ['an abc_size_battery_seed above 1', (d) => (es(d).abc_size_battery_seed = 1.2), 'signals_timeline.forecast_test.effective_size.abc_size_battery_seed: 1.2 is outside [0, 1]'],
    ['an abc_size_second_seed below 0', (d) => (es(d).abc_size_second_seed = -0.01), 'signals_timeline.forecast_test.effective_size.abc_size_second_seed: -0.01 is outside [0, 1]'],
    ['no worst_matched_battery_seed', (d) => delete es(d).worst_matched_battery_seed, 'signals_timeline.forecast_test.effective_size: missing required key "worst_matched_battery_seed"'],
    ['a worst matched rate above 1', (d) => ((es(d).worst_matched_second_seed as Obj).rate = 1.5), 'signals_timeline.forecast_test.effective_size.worst_matched_second_seed.rate: 1.5 is outside [0, 1]'],
    ['an empty worst matched null_side', (d) => ((es(d).worst_matched_battery_seed as Obj).null_side = ''), 'signals_timeline.forecast_test.effective_size.worst_matched_battery_seed.null_side: expected a non-empty string'],
    ['a worst_simulated_size above 1', (d) => ft(d, 'worst_simulated_size', 1.5), 'signals_timeline.forecast_test.worst_simulated_size: 1.5 is outside [0, 1]'],
    ['a decision other than har or naive', (d) => ft(d, 'decision', 'ols'), 'signals_timeline.forecast_test.decision: expected one of "har", "naive"'],
    [
      'a naive decision with p below alpha',
      (d) => ft(d, 'decision', 'naive'),
      'signals_timeline.forecast_test.decision: is "naive" but p 0.012 against threshold 0.025 decides "har"',
    ],
    [
      'a har decision with p at alpha',
      (d) => {
        ft(d, 'p', 0.025)
        ft(d, 'p_holm', 0.025)
      },
      'signals_timeline.forecast_test.decision: is "har" but p 0.025 against threshold 0.025 decides "naive"',
    ],
    ['a label that does not start with proxy', (d) => ft(d, 'label', 'forecast-loss comparison'), 'signals_timeline.forecast_test.label: "forecast-loss comparison" does not start with "proxy"'],
    [
      'an rv_model the test did not choose (naive timeline, har test)',
      (d) => {
        toNaive(d)
        d.forecast_test = copySig().forecast_test
      },
      'signals_timeline.signal.rv_model: is "naive" but the forecast test chose "har"',
    ],
    [
      'an rv_model the test did not choose (har timeline, naive test)',
      (d) => {
        ft(d, 'p', 0.2)
        ft(d, 'p_holm', 0.2)
        ft(d, 'decision', 'naive')
        ft(d, 'ci', [-0.001, 0.004])
      },
      'signals_timeline.signal.rv_model: is "har" but the forecast test chose "naive"',
    ],
    ['a forecast_test that is not an object', (d) => (d.forecast_test = 5 as never), 'signals_timeline.forecast_test: expected an object'],
  ]
  it.each(CASES)('refuses %s', (_name, change, fragment) => rejectsS(change, fragment))

  it('accepts a p of 1 and a worst_simulated_size equal to the worst matched size 0.0815', () => {
    const f = parseSignalsTimeline(
      sig((d) => {
        toNaive(d)
        d.forecast_test = { ...(copySig().forecast_test as Obj), p: 1, p_holm: 1, decision: 'naive', worst_simulated_size: 0.0815, ci: [0.1, 0.1] }
      }),
    )
    expect(f.forecast_test).toMatchObject({ p: 1, worst_simulated_size: 0.0815, ci: [0.1, 0.1] })
  })
})

// ---------------------------------------------------------------- strategy_positions

describe('strategy_positions: the runs', () => {
  const CASES: [string, (d: StratDoc) => void, string][] = [
    ['no runs', (d) => (d.runs = []), 'strategy_positions.runs: needs at least 1 run'],
    ['an empty banner', (d) => (d.banner = ''), 'strategy_positions.banner: expected a non-empty string'],
    ['a strategy that is not the run\'s', (d) => (d.runs[1].strategy = 'Other'), 'strategy_positions.runs[1].strategy: is "Other" but run.strategy is "LongVolOnSignal"'],
    ['params that are not an object', (d) => (d.runs[0].params = [1, 2]), 'strategy_positions.runs[0].params: expected an object'],
    ['an empty trial_group', (d) => (d.runs[0].trial_group = ''), 'strategy_positions.runs[0].trial_group: expected a non-empty string'],
    ['an n_trials_group of 0', (d) => (d.runs[1].n_trials_group = 0), 'strategy_positions.runs[1].n_trials_group: expected a whole number of at least 1, got 0'],
    [
      'position ids that do not increase',
      (d) => (d.runs[0].positions[2].position_id = 2),
      'strategy_positions.runs[0].positions[2].position_id: must be strictly increasing, but 2 follows 2',
    ],
    ['a position_id of 0', (d) => (d.runs[1].positions[0].position_id = 0), 'strategy_positions.runs[1].positions[0].position_id: expected a whole number of at least 1, got 0'],
  ]
  it.each(CASES)('refuses %s', (_name, change, fragment) => rejectsT(change, fragment))

  it('lets position ids restart in the next run', () => {
    expect(parseStrategyPositions(copyStrat()).runs.map((r) => r.positions[0].position_id)).toEqual([1, 1])
  })
})

describe('strategy_positions: a position', () => {
  const P0 = 'strategy_positions.runs[0].positions'
  const pos = (d: StratDoc, run: number, i: number): Pos => d.runs[run].positions[i]
  const CASES: [string, (d: StratDoc) => void, string][] = [
    ['a structure the app does not know', (d) => (pos(d, 0, 0).structure = 'iron_condor'), `${P0}[0].structure: expected one of "short_straddle"`],
    ['an opened date before the run\'s sample', (d) => (pos(d, 0, 0).opened = '2017-12-29'), `${P0}[0].opened: 2017-12-29 is outside the run's sample 2018-01-02 to 2019-12-31`],
    ['an opened date that does not exist', (d) => (pos(d, 0, 0).opened = '2018-02-30'), `${P0}[0].opened: "2018-02-30" is not a calendar date`],
    ['a close before the open', (d) => (pos(d, 0, 0).closed = '2018-02-02'), `${P0}[0].closed: 2018-02-02 is before opened 2018-02-05`],
    ['a close after the run\'s sample', (d) => (pos(d, 1, 0).closed = '2019-07-01'), `strategy_positions.runs[1].positions[0].closed: 2019-07-01 is outside the run's sample`],
    [
      'an exit reason on an open position',
      (d) => (pos(d, 0, 3).exit_reason = 'signal'),
      `${P0}[3].exit_reason: is "signal" but the position is open (closed is null), so this must be null`,
    ],
    ['no exit reason on a closed position', (d) => (pos(d, 0, 0).exit_reason = null), `${P0}[0].exit_reason: is null but the position closed on 2018-02-16`],
    ['an exit reason the app does not know', (d) => (pos(d, 0, 0).exit_reason = 'boredom'), `${P0}[0].exit_reason: expected one of "dte"`],
    ['an entry_signal that is not a number', (d) => (pos(d, 0, 0).entry_signal = 'high'), `${P0}[0].entry_signal: expected a finite number, got high`],
    ['a missing entry_signal key', (d) => delete pos(d, 0, 0).entry_signal, `${P0}[0]: missing required key "entry_signal"`],
    ['a ratio of 2', (d) => (pos(d, 0, 0).legs[0].ratio = 2), `${P0}[0].legs[0].ratio: expected 1 or -1, got 2`],
    ['a ratio of 0', (d) => (pos(d, 0, 0).legs[1].ratio = 0), `${P0}[0].legs[1].ratio: expected 1 or -1, got 0`],
    ['an invalid OSI symbol', (d) => (pos(d, 0, 0).legs[0].osi_symbol = 'SPY 180316C270'), `${P0}[0].legs[0].osi_symbol: "SPY 180316C270" is not a 21-character OSI symbol`],
    [
      'an opening on the expiry day of a leg',
      (d) => {
        pos(d, 0, 0).opened = '2018-03-16'
        pos(d, 0, 0).closed = '2018-03-20'
      },
      `${P0}[0].opened: 2018-03-16 is not before the expiry 2018-03-16`,
    ],
    ['no legs', (d) => (pos(d, 0, 0).legs = []), `${P0}[0].legs: a short_straddle has 2 legs, got 0`],
  ]
  it.each(CASES)('refuses %s', (_name, change, fragment) => rejectsT(change, fragment))

  it('accepts an opening the day before a leg expires, and a position closed on the opening day or on the sample\'s last day', () => {
    const f = parseStrategyPositions(
      strat((d) => {
        pos(d, 0, 0).opened = '2018-03-15'
        pos(d, 0, 0).closed = '2018-03-15'
        pos(d, 1, 0).closed = '2019-06-28'
      }),
    )
    expect(f.runs[0].positions[0]).toMatchObject({ opened: '2018-03-15', closed: '2018-03-15' })
    expect(f.runs[1].positions[0].closed).toBe('2019-06-28')
  })
})

describe('strategy_positions: the legs of each structure', () => {
  const C = (ymd: string, strike: number, ratio: number): Obj => ({ osi_symbol: OSI(ymd, 'C', strike), ratio })
  const Pt = (ymd: string, strike: number, ratio: number): Obj => ({ osi_symbol: OSI(ymd, 'P', strike), ratio })
  /** Replace the legs of the first run's position `i` (and its structure), keeping the rest. */
  const legsOf =
    (i: number, structure: string, legs: Obj[]) =>
    (d: StratDoc): void => {
      d.runs[0].positions[i].structure = structure
      d.runs[0].positions[i].legs = legs
    }
  const AT = 'strategy_positions.runs[0].positions[0].legs'
  const CASES: [string, (d: StratDoc) => void, string][] = [
    ['a short_straddle of three legs', legsOf(0, 'short_straddle', [C('180316', 270, -1), Pt('180316', 270, -1), Pt('180316', 270, -1)]), `${AT}: a short_straddle has 2 legs, got 3`],
    ['a short_straddle of two calls', legsOf(0, 'short_straddle', [C('180316', 270, -1), C('180316', 270, -1)]), `${AT}: a short_straddle has one call and one put, got 2 call(s) and 0 put(s)`],
    ['a short_straddle of two expiries', legsOf(0, 'short_straddle', [C('180316', 270, -1), Pt('180323', 270, -1)]), `${AT}: a short_straddle has one expiry, got 2`],
    ['a short_straddle of two strikes', legsOf(0, 'short_straddle', [C('180316', 270, -1), Pt('180316', 265, -1)]), `${AT}: a short_straddle has one strike, got 2`],
    ['a short_straddle with a long leg', legsOf(0, 'short_straddle', [C('180316', 270, -1), Pt('180316', 270, 1)]), `${AT}[1].ratio: is 1 but every leg of a short_straddle has ratio -1`],
    ['a long_straddle with a short leg', (d) => (d.runs[1].positions[0].legs[0].ratio = -1), 'strategy_positions.runs[1].positions[0].legs[0].ratio: is -1 but every leg of a long_straddle has ratio 1'],
    ['a long_straddle of two expiries', (d) => (d.runs[1].positions[0].legs[1] = Pt('160422', 200, 1)), 'strategy_positions.runs[1].positions[0].legs: a long_straddle has one expiry, got 2'],
    ['a short_strangle of two calls', legsOf(1, 'short_strangle', [C('180518', 285, -1), C('180518', 260, -1)]), 'strategy_positions.runs[0].positions[1].legs: a short_strangle has one call and one put, got 2 call(s)'],
    ['a short_strangle of two expiries', legsOf(1, 'short_strangle', [C('180518', 285, -1), Pt('180511', 260, -1)]), 'strategy_positions.runs[0].positions[1].legs: a short_strangle has one expiry, got 2'],
    ['a short_strangle with a long leg', legsOf(1, 'short_strangle', [C('180518', 285, -1), Pt('180518', 260, 1)]), 'strategy_positions.runs[0].positions[1].legs[1].ratio: is 1 but every leg of a short_strangle has ratio -1'],
    ['a short_strangle whose call strike is below the put strike', legsOf(1, 'short_strangle', [C('180518', 255, -1), Pt('180518', 260, -1)]), 'strategy_positions.runs[0].positions[1].legs: the call strike 255 is not above the put strike 260'],
    ['a short_strangle whose strikes are equal', legsOf(1, 'short_strangle', [C('180518', 260, -1), Pt('180518', 260, -1)]), 'strategy_positions.runs[0].positions[1].legs: the call strike 260 is not above the put strike 260'],
    ['a straddle_calendar of two legs', legsOf(2, 'straddle_calendar', [C('180921', 290, -1), Pt('180921', 290, -1)]), 'strategy_positions.runs[0].positions[2].legs: a straddle_calendar has 4 legs, got 2'],
    [
      'a straddle_calendar of two strikes',
      legsOf(2, 'straddle_calendar', [C('180921', 290, -1), Pt('180921', 290, -1), C('181019', 295, 1), Pt('181019', 295, 1)]),
      'strategy_positions.runs[0].positions[2].legs: a straddle_calendar has one strike, got 2',
    ],
    [
      'a straddle_calendar of one expiry',
      legsOf(2, 'straddle_calendar', [C('180921', 290, -1), Pt('180921', 290, -1), C('180921', 290, 1), Pt('180921', 290, 1)]),
      'strategy_positions.runs[0].positions[2].legs: a straddle_calendar has two expiries, got 1',
    ],
    [
      'a straddle_calendar of three expiries',
      legsOf(2, 'straddle_calendar', [C('180921', 290, -1), Pt('180921', 290, -1), C('181019', 290, 1), Pt('181116', 290, 1)]),
      'strategy_positions.runs[0].positions[2].legs: a straddle_calendar has two expiries, got 3',
    ],
    [
      'a straddle_calendar with two calls on one expiry',
      legsOf(2, 'straddle_calendar', [C('180921', 290, -1), C('180921', 290, -1), Pt('181019', 290, 1), Pt('181019', 290, 1)]),
      'strategy_positions.runs[0].positions[2].legs: a straddle_calendar has a call and a put on each expiry, but 2018-09-21 has 2 leg(s)',
    ],
    [
      'a straddle_calendar with three legs on one expiry',
      legsOf(2, 'straddle_calendar', [C('180921', 290, -1), Pt('180921', 290, -1), Pt('180921', 290, -1), C('181019', 290, 1)]),
      'strategy_positions.runs[0].positions[2].legs: a straddle_calendar has a call and a put on each expiry, but 2018-09-21 has 3 leg(s)',
    ],
    [
      'a straddle_calendar long the nearer expiry',
      legsOf(2, 'straddle_calendar', [C('180921', 290, 1), Pt('180921', 290, 1), C('181019', 290, -1), Pt('181019', 290, -1)]),
      'strategy_positions.runs[0].positions[2].legs[0].ratio: is 1 but the nearer expiry\'s legs of a straddle_calendar have ratio -1',
    ],
    [
      'a straddle_calendar short the farther expiry',
      legsOf(2, 'straddle_calendar', [C('180921', 290, -1), Pt('180921', 290, -1), C('181019', 290, 1), Pt('181019', 290, -1)]),
      'strategy_positions.runs[0].positions[2].legs[3].ratio: is -1 but the farther expiry\'s legs of a straddle_calendar have ratio 1',
    ],
  ]
  it.each(CASES)('refuses %s', (_name, change, fragment) => rejectsT(change, fragment))

  it('accepts a short_strangle whose call strike is one tick above the put strike', () => {
    const f = parseStrategyPositions(strat(legsOf(1, 'short_strangle', [C('180518', 260.5, -1), Pt('180518', 260, -1)])))
    expect(f.runs[0].positions[1].legs.map((l) => l.osi_symbol)).toEqual([OSI('180518', 'C', 260.5), OSI('180518', 'P', 260)])
  })
})
