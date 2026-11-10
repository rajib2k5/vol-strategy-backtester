import { AppShell, type ShellPage } from './lib/shell'
import { useAppData } from './data/useAppData'
import { AboutPage } from './views/AboutPage'
import { ArchitecturePage } from './views/ArchitecturePage'
import { BlotterPage } from './views/BlotterPage'
import { DataQualityPage } from './views/DataQualityPage'
import { PositionsPage } from './views/PositionsPage'
import { SignalPage } from './views/SignalPage'
import { StrategiesPage } from './views/StrategiesPage'
import { SurfacePage } from './views/SurfacePage'
import { PITCH, TITLE } from './content/about'

export const APP_SLUG = 'vol-strategy-backtester'

export default function App() {
  // Loaded once here, so switching tabs never refetches.
  const data = useAppData()
  // The milestone-4 tabs exist once the data is loaded and the manifest lists their dataset (the real export is not committed yet).
  const ready = data.status === 'ready' ? data.data : null
  const m4Pages: ShellPage[] = [
    ...(ready?.signalsTimeline ? [{ id: 'signal', label: 'Signal', render: () => <SignalPage state={data} /> }] : []),
    ...(ready?.strategyPositions ? [{ id: 'strategies', label: 'Strategies', render: () => <StrategiesPage state={data} /> }] : []),
  ]
  return (
    <AppShell
      slug={APP_SLUG}
      title={TITLE}
      subtitle={PITCH}
      pages={[
        { id: 'about', label: 'About', render: () => <AboutPage state={data} /> },
        { id: 'surface', label: 'Surface', render: () => <SurfacePage state={data} /> },
        { id: 'blotter', label: 'Blotter', render: () => <BlotterPage state={data} /> },
        { id: 'positions', label: 'Positions', render: () => <PositionsPage state={data} /> },
        ...m4Pages,
        { id: 'data-quality', label: 'Data quality', render: () => <DataQualityPage state={data} /> },
        { id: 'architecture', label: 'Architecture', render: () => <ArchitecturePage /> },
      ]}
    />
  )
}
