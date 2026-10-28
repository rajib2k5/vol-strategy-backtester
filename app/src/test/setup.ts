import '@testing-library/jest-dom/vitest'

// jsdom has no canvas: its getContext() logs "Not implemented" and returns null. Make that quiet
// and explicit (null = "no WebGL"). Tests that need a context spy on this and override it.
HTMLCanvasElement.prototype.getContext = () => null
