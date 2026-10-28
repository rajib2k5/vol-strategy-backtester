/**
 * Stand-in for @react-three/fiber in jsdom tests (jsdom has no WebGL). Use it with:
 *   vi.mock('@react-three/fiber', () => import('../test/mockFiber'))
 * Canvas renders a marker div, ignores its 3D children, records the props it was given (so a test
 * can check settings such as `flat`), and can be told to throw.
 */
import { createElement, type ReactNode } from 'react'
import { canvasControl } from './mockFiberControl'

export function Canvas(props: { 'aria-label'?: string; children?: ReactNode } & Record<string, unknown>) {
  if (canvasControl.shouldThrow) throw new Error('WebGL context lost')
  canvasControl.lastProps = props
  return createElement('div', { 'data-testid': 'r3f-canvas', 'aria-label': props['aria-label'] })
}

/** Hooks the scene components call; never run, because the mocked Canvas does not render its children. */
export const useFrame = () => undefined
export const useThree = () => undefined
