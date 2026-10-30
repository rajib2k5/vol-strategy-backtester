import { AppShell } from './lib/shell'
import { useAppData } from './data/useAppData'
import { AboutPage } from './views/AboutPage'
import { ArchitecturePage } from './views/ArchitecturePage'
import { DataQualityPage } from './views/DataQualityPage'
import { SurfacePage } from './views/SurfacePage'
import { PITCH, TITLE } from './content/about'

export const APP_SLUG = 'vol-strategy-backtester'

export default function App() {
  // Loaded once here, so switching tabs never refetches.
  const data = useAppData()
  return (
    <AppShell
      slug={APP_SLUG}
      title={TITLE}
      subtitle={PITCH}
      pages={[
        { id: 'about', label: 'About', render: () => <AboutPage state={data} /> },
        { id: 'surface', label: 'Surface', render: () => <SurfacePage state={data} /> },
        { id: 'data-quality', label: 'Data quality', render: () => <DataQualityPage state={data} /> },
        { id: 'architecture', label: 'Architecture', render: () => <ArchitecturePage /> },
      ]}
    />
  )
}
