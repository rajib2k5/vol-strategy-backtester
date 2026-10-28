/**
 * App shell: primary navigation (hash-routed tabs) and the light/dark theme toggle.
 * Markup is fixed and semantic; the stylesheet decides the visual identity purely via
 * CSS on the shell-* classes.
 */
import { useState, useEffect, type ReactNode } from 'react'
import { safeStorage, type StorageLike } from './storage'
import { applyTheme, getStoredTheme, setStoredTheme, type ThemeName } from './theme'

export interface ShellPage {
  id: string
  label: string
  render: () => ReactNode
}

function readRoute(fallback: string): string {
  const m = /^#\/([a-z0-9-]+)/i.exec(window.location.hash)
  return m ? m[1] : fallback
}

export function AppShell({
  slug,
  title,
  subtitle,
  pages,
  storage = safeStorage(),
  defaultTheme = 'dark',
}: {
  slug: string
  title: string
  subtitle?: string
  pages: ShellPage[]
  storage?: StorageLike | null
  defaultTheme?: ThemeName
}) {
  const fallback = pages[0]?.id ?? ''
  const [theme, setTheme] = useState<ThemeName>(() => getStoredTheme(slug, storage) ?? defaultTheme)
  useEffect(() => {
    applyTheme(theme)
  }, [theme])
  const toggleTheme = () => {
    const next: ThemeName = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setStoredTheme(slug, next, storage)
  }
  const [route, setRoute] = useState(() => readRoute(fallback))
  useEffect(() => {
    const on = () => setRoute(readRoute(fallback))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [fallback])

  const activeId = pages.some((p) => p.id === route) ? route : fallback
  const activePage = pages.find((p) => p.id === activeId)

  const go = (id: string) => (e: { preventDefault: () => void }) => {
    e.preventDefault()
    if (window.location.hash !== `#/${id}`) window.location.hash = `#/${id}`
    setRoute(id)
  }

  return (
    <div className="shell">
      <header className="shell-head">
        <div className="shell-brand">
          <h1>{title}</h1>
          {subtitle && <p className="sub">{subtitle}</p>}
        </div>
        <div className="shell-right">
          <nav className="shell-nav" aria-label="Primary">
            {pages.map((p) => (
              <a key={p.id} href={`#/${p.id}`} onClick={go(p.id)} aria-current={p.id === activeId ? 'page' : undefined} className={p.id === activeId ? 'active' : ''}>
                {p.label}
              </a>
            ))}
          </nav>
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
          >
            {theme === 'dark' ? (
              /* sun glyph: switch to light */
              <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
                <circle cx="7.5" cy="7.5" r="3.2" />
                <path d="M7.5 0.8v1.8M7.5 12.4v1.8M0.8 7.5h1.8M12.4 7.5h1.8M2.8 2.8l1.3 1.3M10.9 10.9l1.3 1.3M12.2 2.8l-1.3 1.3M4.1 10.9l-1.3 1.3" />
              </svg>
            ) : (
              /* moon glyph: switch to dark */
              <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
                <path d="M12.8 9.2A5.7 5.7 0 1 1 5.8 2.2a4.6 4.6 0 0 0 7 7z" />
              </svg>
            )}
          </button>
        </div>
      </header>
      <main className="shell-main">{activePage?.render()}</main>
    </div>
  )
}
