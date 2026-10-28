import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { ActivityDiagram, ArchDiagram, SequenceDiagram } from '../lib/diagrams'
import { ACTORS, EDGES, LAYERS, NODES, STEPS } from './architecture'

// These tests guard the internal consistency of the content, so a revision made when a decision
// record changes cannot leave a diagram pointing at something that no longer exists, or print a
// label the diagram has no room for. The fit checks render the real diagram components and read
// the geometry they produce, rather than repeating the layout arithmetic here.

/** The diagrams use a monospace face, whose advance is about 0.6 em per character. */
const EM = 0.6

const attr = (el: Element, name: string) => Number(el.getAttribute(name))

function textWidth(el: Element): number {
  return (el.textContent ?? '').length * attr(el, 'font-size') * EM
}

/** Left and right edge of a <text>, from its x, its text-anchor and its measured width. */
function textSpan(el: Element): [number, number] {
  const x = attr(el, 'x')
  const w = textWidth(el)
  return el.getAttribute('text-anchor') === 'middle' ? [x - w / 2, x + w / 2] : [x, x + w]
}

function expectTextInsideViewBox(svg: Element, what: string) {
  const width = Number(svg.getAttribute('viewBox')?.split(' ')[2])
  expect(width).toBeGreaterThan(0)
  for (const t of svg.querySelectorAll('text')) {
    const [left, right] = textSpan(t)
    expect(left, `${what}: "${t.textContent}" starts left of the diagram`).toBeGreaterThanOrEqual(0)
    expect(right, `${what}: "${t.textContent}" runs past the right edge`).toBeLessThanOrEqual(width)
  }
}

/** Every group that holds one rectangle and one text: the text must fit inside the rectangle. */
function expectLabelsFitTheirRects(groups: Iterable<Element>, what: string) {
  let checked = 0
  for (const g of groups) {
    const rect = g.querySelector(':scope > rect')
    const text = g.querySelector(':scope > text')
    if (!rect || !text) continue
    checked++
    expect(textWidth(text), `${what}: "${text.textContent}" is wider than its box`).toBeLessThanOrEqual(attr(rect, 'width'))
  }
  return checked
}

describe('architecture layers', () => {
  it('draws the sources first and the app last, so the picture reads in data-flow order', () => {
    expect(LAYERS[0].label).toBe('Sources')
    expect(LAYERS[LAYERS.length - 1].label).toBe('App')
  })
  it('has unique layer labels, at least one box each, unique box labels and a non-empty detail', () => {
    expect(new Set(LAYERS.map((l) => l.label)).size).toBe(LAYERS.length)
    for (const l of LAYERS) {
      expect(l.boxes.length, l.label).toBeGreaterThan(0)
      expect(l.detail.trim().length, `${l.label} detail`).toBeGreaterThan(0)
    }
    // The page looks boxes up by their text, so a repeat anywhere in the picture would be ambiguous.
    const boxes = LAYERS.flatMap((l) => l.boxes)
    expect(new Set(boxes).size).toBe(boxes.length)
  })
  it('keeps every box label inside its box and every layer title clear of the boxes', () => {
    const { container } = render(<ArchDiagram layers={LAYERS} />)
    const layers = container.querySelectorAll('.vsb-arch-layer')
    expect(layers).toHaveLength(LAYERS.length)
    const checked = expectLabelsFitTheirRects(container.querySelectorAll('.vsb-arch-layer > g'), 'architecture')
    expect(checked).toBe(LAYERS.flatMap((l) => l.boxes).length)
    for (const layer of layers) {
      const title = layer.querySelector(':scope > text')!
      const firstBoxLeft = attr(layer.querySelector('rect')!, 'x')
      // letter-spacing="1" adds one unit per character on top of the glyph advance.
      const right = attr(title, 'x') + textWidth(title) + (title.textContent ?? '').length
      expect(right, `layer title "${title.textContent}"`).toBeLessThan(firstBoxLeft)
    }
  })
})

describe('daily-loop sequence', () => {
  it('has distinct, non-empty actor names', () => {
    expect(new Set(ACTORS).size).toBe(ACTORS.length)
    for (const a of ACTORS) expect(a.trim().length).toBeGreaterThan(0)
  })
  it('only references actors that exist, and has a non-empty label on every step', () => {
    for (const [i, s] of STEPS.entries()) {
      expect(Number.isInteger(s.from) && s.from >= 0 && s.from < ACTORS.length, `step ${i} from`).toBe(true)
      expect(Number.isInteger(s.to) && s.to >= 0 && s.to < ACTORS.length, `step ${i} to`).toBe(true)
      expect(s.label.trim().length, `step ${i} label`).toBeGreaterThan(0)
    }
  })
  it('gives every actor at least one message, so no lifeline is drawn for nothing', () => {
    const used = new Set(STEPS.flatMap((s) => [s.from, s.to]))
    for (const [i, a] of ACTORS.entries()) expect(used.has(i), `${a} takes part in no step`).toBe(true)
  })
  it('starts with the Engine loading from the Store and ends with the Engine writing the Ledger', () => {
    expect(STEPS[0]).toMatchObject({ from: 0, to: ACTORS.indexOf('Store') })
    expect(STEPS[STEPS.length - 1]).toMatchObject({ from: 0, to: ACTORS.indexOf('Ledger') })
  })
  it('walks the eleven steps of ADR-0001 in order, each with at least one message', () => {
    const ADR_STEPS = 11
    const tags = STEPS.map((s) => s.adr)
    expect([...tags].sort((a, b) => a - b)).toEqual(tags)
    expect(new Set(tags)).toEqual(new Set(Array.from({ length: ADR_STEPS }, (_, i) => i + 1)))
  })
  it('puts fills before expiry, expiry before marks, marks before the hedge and the hedge before the ledger write', () => {
    // ADR-0001: yesterday's orders fill at today's quotes first, so every new lot is marked on its fill day.
    const labels = STEPS.map((s) => s.label)
    const positions = ['fill', 'settle', 'mark', 'hedge', 'write the ledger'].map((needle) => labels.findIndex((l) => l.includes(needle)))
    expect(positions.every((p) => p >= 0), `missing step in ${JSON.stringify(positions)}`).toBe(true)
    expect([...positions].sort((a, b) => a - b)).toEqual(positions)
    expect(new Set(positions).size).toBe(positions.length)
  })
  it('keeps strategies and signals away from the store: neither ever talks to the Store', () => {
    // ADR-0001 section 4: strategies and signals see a MarketView, never the store directly.
    const store = ACTORS.indexOf('Store')
    for (const name of ['Strat', 'Signals']) {
      const actor = ACTORS.indexOf(name)
      expect(actor, `${name} is an actor`).toBeGreaterThanOrEqual(0)
      for (const s of STEPS) {
        const ends = [s.from, s.to]
        if (ends.includes(actor)) expect(ends.includes(store), `"${s.label}" connects ${name} and Store`).toBe(false)
      }
    }
  })
  it('has the engine call signals, which read the View, before the strategies decide', () => {
    // ADR-0001 step 9 and section 2: signals are computed causally from the MarketView, then the strategies decide.
    const [engine, view, signals, strat] = ['Engine', 'View', 'Signals', 'Strat'].map((a) => ACTORS.indexOf(a))
    const at = (from: number, to: number) => STEPS.findIndex((s) => s.from === from && s.to === to)
    const call = at(engine, signals)
    const read = at(signals, view)
    const result = at(signals, engine)
    const decide = at(engine, strat)
    expect([call, read, result, decide].every((i) => i >= 0), `missing step in ${JSON.stringify([call, read, result, decide])}`).toBe(true)
    expect([call, read, result, decide]).toEqual([call, read, result, decide].sort((a, b) => a - b))
    expect(new Set([call, read, result, decide]).size).toBe(4)
  })
  it('books assignments first, then cancels the orders on the lots they removed, and only then fills', () => {
    // ADR-0001 step 2 and test 7: the order on an assigned lot is cancelled (LOT_REMOVED), never filled against a lot no longer held.
    const labels = STEPS.map((s) => s.label)
    const positions = ['book assignments', 'LOT_REMOVED', 'fill orders'].map((needle) => labels.findIndex((l) => l.includes(needle)))
    expect(positions.every((p) => p >= 0), `missing step in ${JSON.stringify(positions)}`).toBe(true)
    expect([...positions].sort((a, b) => a - b)).toEqual(positions)
    expect(new Set(positions).size).toBe(positions.length)
    const adr = (needle: string) => STEPS[labels.findIndex((l) => l.includes(needle))].adr
    expect([adr('book assignments'), adr('LOT_REMOVED'), adr('fill orders')]).toEqual([2, 2, 3])
  })
  it('lets only the Engine write to the Ledger', () => {
    const ledger = ACTORS.indexOf('Ledger')
    const engine = ACTORS.indexOf('Engine')
    for (const s of STEPS) if (s.from === ledger || s.to === ledger) expect([s.from, s.to], `"${s.label}"`).toEqual([engine, ledger])
  })
  it('fits every actor name in its header box and every message label inside the diagram', () => {
    const { container } = render(<SequenceDiagram actors={ACTORS} steps={STEPS} />)
    const svg = container.querySelector('svg')!
    expect(expectLabelsFitTheirRects(svg.querySelectorAll(':scope > g'), 'sequence')).toBe(ACTORS.length)
    expectTextInsideViewBox(svg, 'sequence')
  })
})

describe('research-process activity diagram', () => {
  const ids = NODES.map((n) => n.id)
  const index = (id: string) => ids.indexOf(id)
  const outgoing = (id: string) => EDGES.filter((e) => e.from === id)
  const isBack = (e: (typeof EDGES)[number]) => index(e.to) < index(e.from)

  it('has unique node ids and labels, exactly one start and one end', () => {
    expect(new Set(ids).size).toBe(ids.length)
    expect(new Set(NODES.map((n) => n.label)).size).toBe(NODES.length)
    expect(NODES.filter((n) => n.type === 'start')).toHaveLength(1)
    expect(NODES.filter((n) => n.type === 'end')).toHaveLength(1)
    expect(NODES[0].type).toBe('start')
    expect(NODES[NODES.length - 1].type).toBe('end')
  })
  it('only has edges between nodes that exist, with no self-loops or repeated edges', () => {
    for (const e of EDGES) {
      expect(ids, `edge from ${e.from}`).toContain(e.from)
      expect(ids, `edge to ${e.to}`).toContain(e.to)
      expect(e.from, 'self-loop').not.toBe(e.to)
    }
    const pairs = EDGES.map((e) => `${e.from}->${e.to}`)
    expect(new Set(pairs).size).toBe(pairs.length)
  })
  it('chains every node to the next one in the order they are listed', () => {
    for (let i = 0; i < ids.length - 1; i++) {
      expect(EDGES.some((e) => e.from === ids[i] && e.to === ids[i + 1]), `${ids[i]} -> ${ids[i + 1]}`).toBe(true)
    }
  })
  it('lets every node be reached from the start, and the end be reached from every node', () => {
    const reach = (from: string, next: (id: string) => string[]) => {
      const seen = new Set<string>([from])
      const queue = [from]
      while (queue.length) {
        const cur = queue.pop() as string
        for (const n of next(cur)) {
          if (!seen.has(n)) {
            seen.add(n)
            queue.push(n)
          }
        }
      }
      return seen
    }
    const start = NODES.find((n) => n.type === 'start')!.id
    const end = NODES.find((n) => n.type === 'end')!.id
    expect([...reach(start, (id) => outgoing(id).map((e) => e.to))].sort()).toEqual([...ids].sort())
    expect([...reach(end, (id) => EDGES.filter((e) => e.to === id).map((e) => e.from))].sort()).toEqual([...ids].sort())
    expect(outgoing(end), 'the end node has nowhere to go').toHaveLength(0)
  })
  it('branches only at decision nodes, which each offer a labelled way forward and a labelled way back', () => {
    for (const n of NODES) {
      const out = outgoing(n.id)
      if (n.type !== 'decision') {
        expect(out.length, `${n.id} is not a decision but branches`).toBeLessThanOrEqual(1)
        continue
      }
      expect(out.length, `${n.id} needs two outcomes`).toBeGreaterThanOrEqual(2)
      for (const e of out) expect(e.label?.trim(), `${n.id} -> ${e.to} needs a label`).toBeTruthy()
      expect(out.some(isBack), `${n.id} never sends work back`).toBe(true)
      expect(out.some((e) => !isBack(e)), `${n.id} never lets work through`).toBe(true)
    }
  })
  it('sends work backwards only from decision nodes, so a loop is always a failed gate or a refuted review', () => {
    const decisions = new Set(NODES.filter((n) => n.type === 'decision').map((n) => n.id))
    for (const e of EDGES.filter(isBack)) expect(decisions.has(e.from), `${e.from} -> ${e.to}`).toBe(true)
  })
  it('fits every node label in its shape and every edge label inside the diagram', () => {
    const { container } = render(<ActivityDiagram nodes={NODES} edges={EDGES} />)
    const svg = container.querySelector('svg')!
    const groups = svg.querySelectorAll(':scope > g')
    const actions = NODES.filter((n) => (n.type ?? 'action') === 'action')
    expect(expectLabelsFitTheirRects(groups, 'activity')).toBe(actions.length)
    // A diamond is only as wide as its label at the middle line: keep the text inside the middle ~70%.
    const diamonds = [...groups].filter((g) => g.querySelector(':scope > polygon'))
    expect(diamonds).toHaveLength(NODES.filter((n) => n.type === 'decision').length)
    for (const g of diamonds) {
      const xs = (g.querySelector('polygon')!.getAttribute('points') ?? '').split(' ').map((p) => Number(p.split(',')[0]))
      const width = Math.max(...xs) - Math.min(...xs)
      expect(textWidth(g.querySelector('text')!), `"${g.querySelector('text')!.textContent}" in a diamond`).toBeLessThanOrEqual(width * 0.7)
    }
    expectTextInsideViewBox(svg, 'activity')
  })
})
