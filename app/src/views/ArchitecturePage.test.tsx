import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { ArchitecturePage } from './ArchitecturePage'
import { ACTORS, LAYERS, NODES } from '../content/architecture'

describe('ArchitecturePage', () => {
  it('renders the architecture, sequence and activity diagrams', () => {
    render(<ArchitecturePage />)
    expect(screen.getByRole('img', { name: 'Architecture diagram' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Sequence diagram' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Activity diagram' })).toBeInTheDocument()
  })

  it('draws every layer, actor and process step from the content module', () => {
    render(<ArchitecturePage />)
    const arch = screen.getByRole('img', { name: 'Architecture diagram' })
    for (const l of LAYERS) {
      expect(within(arch).getByText(l.label.toUpperCase())).toBeInTheDocument()
      for (const b of l.boxes) expect(within(arch).getByText(b)).toBeInTheDocument()
    }
    const seq = screen.getByRole('img', { name: 'Sequence diagram' })
    for (const a of ACTORS) expect(within(seq).getByText(a)).toBeInTheDocument()
    const act = screen.getByRole('img', { name: 'Activity diagram' })
    for (const n of NODES) expect(within(act).getByText(n.label)).toBeInTheDocument()
  })

  it('prints each layer detail beside the diagram', () => {
    render(<ArchitecturePage />)
    for (const l of LAYERS) expect(screen.getByText(l.detail)).toBeInTheDocument()
  })
})
