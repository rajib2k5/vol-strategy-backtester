import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AppShell } from './shell'
import { resetMemoryFallback, safeStorage } from './storage'

const PAGES = [
  { id: 'about', label: 'About', render: () => <p>about-content</p> },
  { id: 'architecture', label: 'Architecture', render: () => <p>architecture-content</p> },
]

const STORE = safeStorage()

function shell() {
  return <AppShell slug="test-app" title="Test App" subtitle="A test" pages={PAGES} storage={STORE} />
}

beforeEach(() => {
  resetMemoryFallback()
  STORE.removeItem('test-app:theme')
  window.location.hash = ''
  document.documentElement.removeAttribute('data-theme')
})

describe('AppShell navigation', () => {
  it('renders one nav link per page (and no others), first page active', () => {
    render(shell())
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    const links = Array.from(nav.querySelectorAll('a')).map((a) => a.textContent)
    expect(links).toEqual(['About', 'Architecture'])
    expect(screen.getByText('about-content')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'About' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Architecture' })).not.toHaveAttribute('aria-current')
  })
  it('shows the title and subtitle', () => {
    render(shell())
    expect(screen.getByRole('heading', { level: 1, name: 'Test App' })).toBeInTheDocument()
    expect(screen.getByText('A test')).toBeInTheDocument()
  })
  it('switches pages on nav click and updates the hash', () => {
    render(shell())
    fireEvent.click(screen.getByRole('link', { name: 'Architecture' }))
    expect(screen.getByText('architecture-content')).toBeInTheDocument()
    expect(screen.queryByText('about-content')).not.toBeInTheDocument()
    expect(window.location.hash).toBe('#/architecture')
  })
  it('opens the page named in the URL hash on mount, and follows hashchange events', () => {
    window.location.hash = '#/architecture'
    render(shell())
    expect(screen.getByText('architecture-content')).toBeInTheDocument()
    window.location.hash = '#/about'
    fireEvent(window, new HashChangeEvent('hashchange'))
    expect(screen.getByText('about-content')).toBeInTheDocument()
  })
  it('falls back to the first page for an unknown route', () => {
    window.location.hash = '#/does-not-exist'
    render(shell())
    expect(screen.getByText('about-content')).toBeInTheDocument()
  })
  it('renders an empty main region (no crash) when given no pages', () => {
    render(<AppShell slug="test-app" title="T" pages={[]} storage={STORE} />)
    expect(screen.getByRole('main')).toBeEmptyDOMElement()
  })
})

describe('Theme toggle', () => {
  it('toggles light/dark on the document element and persists the choice', () => {
    render(shell())
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    expect(STORE.getItem('test-app:theme')).toBe('light')
    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(STORE.getItem('test-app:theme')).toBe('dark')
  })
  it('honors a stored theme preference on mount', () => {
    STORE.setItem('test-app:theme', 'light')
    render(shell())
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
  })
  it('uses defaultTheme when nothing is stored', () => {
    render(<AppShell slug="test-app" title="T" pages={PAGES} storage={STORE} defaultTheme="light" />)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})
