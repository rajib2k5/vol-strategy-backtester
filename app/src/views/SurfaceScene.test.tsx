/**
 * Renders the REAL scene components into a three.js scene graph with @react-three/test-renderer
 * (a fake GPU: nothing is drawn, but every object, buffer and material is created for real), and
 * checks what ends up where. SurfaceHero.test.tsx cannot do this: jsdom has no WebGL, so it swaps
 * <Canvas> for a stub that ignores its children.
 *
 * Expected values are worked out by hand on a 2 x 2 grid; see surfaceGeometry.test.ts for the same
 * grid derived step by step.
 */
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import { PerspectiveCamera, type BufferGeometry, type LineSegments, type Mesh, type MeshBasicMaterial } from 'three'
import { SceneContents } from './SurfaceHero'
import { axisLabels, buildSurfaceGeometry, type AxisLabel } from '../lib/surfaceGeometry'
import { BASE_FOV } from '../lib/framing'

// Recorded by the stand-in below, so the test can read the props OrbitControls was given.
const orbit = vi.hoisted(() => ({ props: null as Record<string, unknown> | null }))
vi.mock('@react-three/drei', () => ({
  OrbitControls: (props: Record<string, unknown>) => {
    orbit.props = props
    return null
  },
}))

// test-renderer wraps its work in React's act(); tell React that is intended (otherwise it warns),
// and silence three's one-line Clock deprecation notice that fiber triggers on every render.
const actFlag = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
const wasActEnvironment = actFlag.IS_REACT_ACT_ENVIRONMENT
const realWarn = console.warn.bind(console)
beforeAll(() => {
  actFlag.IS_REACT_ACT_ENVIRONMENT = true
  vi.spyOn(console, 'warn').mockImplementation((...args: unknown[]) => {
    if (!String(args[0]).includes('THREE.Clock')) realWarn(...args)
  })
})
afterAll(() => {
  actFlag.IS_REACT_ACT_ENVIRONMENT = wasActEnvironment
  vi.restoreAllMocks()
})

// moneyness [-0.2, 0.2], dte [10, 30], iv [[0.2, 0.3], [0.4, 0.6]]. Vertex v = i * 2 + j.
const geo = buildSurfaceGeometry([-0.2, 0.2], [10, 30], [[0.2, 0.3], [0.4, 0.6]])

async function renderScene(options: Parameters<typeof ReactThreeTestRenderer.create>[1] = {}) {
  return ReactThreeTestRenderer.create(
    <SceneContents geo={geo} labels={axisLabels(geo.extent)} els={{ current: [] }} />,
    options,
  )
}

const geometryOf = (object: unknown) => (object as Mesh | LineSegments).geometry as BufferGeometry
const numbers = (array: ArrayLike<number> | undefined) => Array.from(array ?? [])
const closeTo = (actual: number[], expected: number[]) => {
  expect(actual).toHaveLength(expected.length)
  expected.forEach((e, i) => expect(actual[i], `element ${i}`).toBeCloseTo(e, 6))
}

describe('SceneContents: the objects in the scene', () => {
  it('draws a filled mesh, then a wireframe, then the axis lines', async () => {
    const renderer = await renderScene()
    expect(renderer.scene.children.map((c) => c.type)).toEqual(['Mesh', 'LineSegments', 'LineSegments'])
  })

  it('gives the mesh the positions in position, the colours in color and the TRIANGLE indices as its index', async () => {
    const renderer = await renderScene()
    const mesh = geometryOf(renderer.scene.children[0].instance)
    // v0..v3 = (x, y, z): y is the normalised IV (0.2 -> 0, 0.3 -> 0.25, 0.4 -> 0.5, 0.6 -> 1).
    closeTo(numbers(mesh.getAttribute('position').array), [0, 0, 0, 1, 0.25, 0, 0, 0.5, 1, 1, 1, 1])
    expect(mesh.getAttribute('position').itemSize).toBe(3)
    // Linear-light ramp colours: the light end for v0 (y = 0), the dark end for v3 (y = 1).
    const colors = numbers(mesh.getAttribute('color').array)
    closeTo(colors.slice(0, 3), [0.238398, 0.467784, 0.863157])
    closeTo(colors.slice(9, 12), [0.009134, 0.078187, 0.300544])
    expect(mesh.getAttribute('color').itemSize).toBe(3)
    // One cell = triangles (a, c, b) and (b, c, d) with a, b, c, d = 0, 1, 2, 3.
    expect(numbers(mesh.index?.array)).toEqual([0, 2, 1, 1, 2, 3])
  })

  it('gives the wireframe the same positions, no colours and the SEGMENT indices', async () => {
    const renderer = await renderScene()
    const wire = geometryOf(renderer.scene.children[1].instance)
    closeTo(numbers(wire.getAttribute('position').array), [0, 0, 0, 1, 0.25, 0, 0, 0.5, 1, 1, 1, 1])
    expect(wire.getAttribute('color')).toBeUndefined()
    // v0-v1, v0-v2, v1-v3, v2-v3: the four edges of the single cell.
    expect(numbers(wire.index?.array)).toEqual([0, 1, 0, 2, 1, 3, 2, 3])
  })

  it('draws the three axes along the front edge, the right edge and the front-left edge', async () => {
    const renderer = await renderScene()
    const axes = geometryOf(renderer.scene.children[2].instance)
    expect(numbers(axes.getAttribute('position').array)).toEqual([
      0, 0, 1, 1, 0, 1, // x axis: front edge
      1, 0, 1, 1, 0, 0, // z axis: right edge
      0, 0, 1, 0, 1, 1, // y axis: front-left edge
    ])
    expect(axes.index).toBeNull()
  })

  it('shades the surface with its vertex colours, unlit and visible from both sides', async () => {
    const renderer = await renderScene()
    const material = (renderer.scene.children[0].instance as Mesh).material as MeshBasicMaterial
    expect(material.type).toBe('MeshBasicMaterial')
    expect(material.vertexColors).toBe(true)
    expect(material.side).toBe(2) // DoubleSide
  })
})

describe('SceneContents: camera controls', () => {
  it('orbits the middle of the surface, with no pan and no wheel zoom', async () => {
    orbit.props = null
    await renderScene()
    expect(orbit.props).toMatchObject({ target: [0.5, 0.35, 0.5], enablePan: false, enableZoom: false })
  })
})

describe('SceneContents: FitCamera', () => {
  // Hand value: below the reference aspect 1.5, tan(fov / 2) = tan(19 deg) * 1.5 / aspect.
  // aspect 120 / 100 = 1.2: tan(fov / 2) = 0.344328 * 1.25 = 0.430410 -> fov / 2 = 23.2875 deg -> 46.575 deg.
  it('widens the field of view on a narrow stage', async () => {
    const camera = new PerspectiveCamera(BASE_FOV, 1, 0.1, 50)
    const update = vi.spyOn(camera, 'updateProjectionMatrix')
    await renderScene({ width: 120, height: 100, camera })
    expect(camera.fov).toBeCloseTo(46.575, 2)
    expect(update).toHaveBeenCalled() // the new fov is only used once the projection is rebuilt
  })

  it('puts a wide stage back on the base field of view', async () => {
    const camera = new PerspectiveCamera(60, 1, 0.1, 50)
    await renderScene({ width: 300, height: 100, camera })
    expect(camera.fov).toBe(BASE_FOV)
  })
})

describe('SceneContents: LabelProjector', () => {
  // Three labels on a camera at (0, 0, 5) looking down -z, on a 300 x 200 stage. That stage is exactly
  // the reference aspect 1.5, so FitCamera leaves the field of view at 38 deg and tan(19 deg) = 0.344328.
  //   centre (0, 0, 0): straight ahead -> NDC (0, 0) -> pixel (150, 100), the middle of the stage.
  //   up     (0, 1, 0): 1 unit up at distance 5 -> NDC y = (1 / 5) / 0.344328 = 0.580842
  //                     -> pixel y = (0.5 - 0.580842 / 2) * 200 = 41.916 (ABOVE the middle, so less than 100).
  //   right  (1, 0, 0): NDC x = (1 / 5) / (0.344328 * 1.5) = 0.387228 -> pixel x = (0.5 + 0.387228 / 2) * 300 = 208.084.
  const labels: AxisLabel[] = [
    { text: 'centre', at: [0, 0, 0], title: false },
    { text: 'up', at: [0, 1, 0], title: false },
    { text: 'right', at: [1, 0, 0], title: false },
  ]

  // Stand-ins for the <span>s Scene3D renders. The stylesheet hides them until their first position.
  const spans = () =>
    labels.map(() => {
      const el = document.createElement('span')
      el.style.visibility = 'hidden'
      return el
    })

  const pixelOf = (el: HTMLElement) => {
    const m = /^translate\((\S+)px, (\S+)px\) translate\(-50%, -50%\)$/.exec(el.style.transform)
    expect(m, `transform was "${el.style.transform}"`).not.toBeNull()
    return { x: Number(m![1]), y: Number(m![2]) }
  }

  async function renderLabelledScene(els: (HTMLSpanElement | null)[]) {
    const camera = new PerspectiveCamera(BASE_FOV, 1.5, 0.1, 50)
    camera.position.set(0, 0, 5)
    return ReactThreeTestRenderer.create(<SceneContents geo={geo} labels={labels} els={{ current: els }} />, {
      width: 300,
      height: 200,
      camera,
    })
  }

  it('leaves the labels hidden until a frame has been drawn', async () => {
    const els = spans()
    await renderLabelledScene(els)
    expect(els.map((el) => el.style.visibility)).toEqual(['hidden', 'hidden', 'hidden'])
  })

  it('shows every label and puts it where its 3D anchor lands on the stage', async () => {
    const els = spans()
    const renderer = await renderLabelledScene(els)
    await renderer.advanceFrames(1, 0.016)

    expect(els.map((el) => el.style.visibility)).toEqual(['visible', 'visible', 'visible'])
    const [centre, up, right] = els.map(pixelOf)
    expect(centre.x).toBeCloseTo(150, 3)
    expect(centre.y).toBeCloseTo(100, 3) // the point the camera looks at is the middle of the stage
    expect(up.x).toBeCloseTo(150, 3)
    expect(up.y).toBeCloseTo(41.916, 2)
    expect(up.y).toBeLessThan(centre.y) // higher in the scene = higher on screen = smaller pixel y
    expect(right.x).toBeCloseTo(208.084, 2)
    expect(right.y).toBeCloseTo(100, 3)
  })

  it('ignores a label that has no element yet', async () => {
    const els = spans()
    const renderer = await renderLabelledScene([els[0], null, els[2]])
    await renderer.advanceFrames(1, 0.016)
    expect(els[0].style.visibility).toBe('visible')
    expect(els[1].style.visibility).toBe('hidden') // never given to the scene, so never touched
    expect(els[2].style.visibility).toBe('visible')
  })
})
