import { ActivityDiagram, ArchDiagram, SequenceDiagram } from '../lib/diagrams'
import { ACTORS, EDGES, LAYERS, NODES, STEPS } from '../content/architecture'

export function ArchitecturePage() {
  return (
    <section className="architecture">
      <h2>Architecture</h2>
      <p className="sub">
        {LAYERS.length} layers in data-flow order. Each module may import only the modules on its explicit allow-list (ADR-0001), which an
        AST test will enforce from M1. The Python engine does all the work; the last two layers hand results to this app as versioned JSON.
      </p>
      <div className="card">
        <ArchDiagram layers={LAYERS} />
      </div>
      <dl className="layer-details">
        {LAYERS.map((l) => (
          <div key={l.label}>
            <dt>{l.label}</dt>
            <dd>{l.detail}</dd>
          </div>
        ))}
      </dl>

      <h2>Sequence: one day of the backtest</h2>
      <div className="card">
        <SequenceDiagram actors={ACTORS} steps={STEPS} />
      </div>

      <h2>Activity: from hypothesis to published result</h2>
      <div className="card">
        <ActivityDiagram nodes={NODES} edges={EDGES} />
      </div>
    </section>
  )
}
