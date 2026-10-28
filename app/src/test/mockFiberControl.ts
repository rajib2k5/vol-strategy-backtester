/** Lets a test make the mocked <Canvas> throw, to exercise SurfaceHero's error boundary. */
export const canvasControl: {
  shouldThrow: boolean
  /** The props the most recent <Canvas> render received (null before the first render). */
  lastProps: Record<string, unknown> | null
} = { shouldThrow: false, lastProps: null }
