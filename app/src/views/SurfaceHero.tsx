/**
 * The 3D hero: an implied-vol surface as a rotatable mesh. The About page draws the illustrative
 * SSVI surface with it; the Surface page draws the real SPY surfaces of surface_frames.json.
 *
 *   x = log-moneyness, y = implied vol (also the colour), z = days to expiry.
 *
 * All of the numbers come from buildSurfaceGeometry, meshAttributes and axisLabels (pure,
 * unit-tested). This file only hands those arrays to three.js through @react-three/fiber and adds
 * orbit controls.
 *
 * Axis labels are plain DOM elements laid over the canvas and re-projected from 3D to screen
 * coordinates every frame. (drei's <Html> would do this for us, but it mounts a second React root
 * per label and unmounting it during render makes React 19 complain and, in StrictMode, can drop
 * labels.)
 *
 * Without WebGL (old browsers, locked-down machines, a lost GPU context) it shows the same grid
 * as a 2D heatmap instead, so the page never ends up with an empty box.
 */
import { Component, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { DoubleSide, PerspectiveCamera, Vector3 } from 'three'
import { axisLabels, buildSurfaceGeometry, type AxisLabel, type SurfaceGeometry } from '../lib/surfaceGeometry'
import { AXIS_SEGMENTS, ORBIT_TARGET, meshAttributes } from '../lib/surfaceScene'
import { RAMP_STOPS } from '../lib/colorRamp'
import { BASE_FOV, fovForAspect } from '../lib/framing'
import { labelTransform, ndcToPixels } from '../lib/labelProjection'
import { Heatmap } from '../lib/charts'
import { fmt, pct } from '../lib/format'
import type { IllustrativeSurface } from '../lib/contract'
import { SURFACE_LABEL } from '../content/about'
import { detectWebGL } from './webgl'

// Grey that stays visible on both the light (#ffffff) and dark (#1a1f29) card.
const GUIDE_GREY = '#8a8f98'

/** Exported so SurfaceScene.test.tsx can render it into a real (fake-GPU) three.js scene. */
export function SurfaceScene({ geo }: { geo: SurfaceGeometry }) {
  const a = meshAttributes(geo)
  return (
    <>
      {/* The surface. Unlit material: the vertex colours ARE the ramp, shading would distort them. */}
      <mesh>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[a.position, 3]} />
          <bufferAttribute attach="attributes-color" args={[a.color, 3]} />
          <bufferAttribute attach="index" args={[a.index, 1]} />
        </bufferGeometry>
        {/* polygonOffset pushes the faces back a hair so the grid lines on top don't z-fight with them */}
        <meshBasicMaterial vertexColors side={DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1} />
      </mesh>
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[a.position, 3]} />
          <bufferAttribute attach="index" args={[a.lineIndex, 1]} />
        </bufferGeometry>
        <lineBasicMaterial color={GUIDE_GREY} transparent opacity={0.5} />
      </lineSegments>
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[AXIS_SEGMENTS, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={GUIDE_GREY} />
      </lineSegments>
      {/* No wheel zoom: it would swallow page scrolling whenever the pointer is over the hero. */}
      <OrbitControls target={ORBIT_TARGET} enablePan={false} enableZoom={false} />
    </>
  )
}

/** Widens the field of view on narrow stages (phones) so the labels are not cropped. Exported for SurfaceScene.test.tsx. */
export function FitCamera() {
  const camera = useThree((s) => s.camera)
  const size = useThree((s) => s.size)
  const invalidate = useThree((s) => s.invalidate)
  useEffect(() => {
    if (!(camera instanceof PerspectiveCamera)) return
    camera.fov = fovForAspect(size.width / size.height)
    camera.updateProjectionMatrix()
    invalidate()
  }, [camera, size, invalidate])
  return null
}

const projected = new Vector3()

/** Each frame, move every label element to where its 3D anchor currently lands on screen. */
function LabelProjector({ labels, els }: { labels: AxisLabel[]; els: RefObject<(HTMLSpanElement | null)[]> }) {
  useFrame(({ camera, size }) => {
    camera.updateMatrixWorld()
    labels.forEach((label, i) => {
      const el = els.current[i]
      if (!el) return
      projected.set(...label.at).project(camera) // -> normalised device coordinates, x and y in [-1, 1]
      el.style.transform = labelTransform(ndcToPixels(projected, size))
      el.style.visibility = 'visible'
    })
  })
  return null
}

/**
 * Everything that lives INSIDE the <Canvas>. It is its own component so a test can render exactly
 * this tree into a fake-GPU three.js scene (SurfaceScene.test.tsx); <Canvas> itself needs WebGL.
 */
export function SceneContents({
  geo,
  labels,
  els,
}: {
  geo: SurfaceGeometry
  labels: AxisLabel[]
  els: RefObject<(HTMLSpanElement | null)[]>
}) {
  return (
    <>
      <SurfaceScene geo={geo} />
      <FitCamera />
      <LabelProjector labels={labels} els={els} />
    </>
  )
}

/** The canvas plus its label overlay. Both live in one place so a failure removes both. */
function Scene3D({ geo }: { geo: SurfaceGeometry }) {
  const labels = useMemo(() => axisLabels(geo.extent), [geo])
  const els = useRef<(HTMLSpanElement | null)[]>([])
  return (
    <>
      {/* `flat` turns off tone mapping. react-three-fiber 9 otherwise applies ACES Filmic to every
          material, which shifts and compresses the colours: the surface would no longer show the
          ramp in colorRamp.ts, and the CSS legend below (drawn from the same stops) would not
          match what is on screen. */}
      <Canvas
        flat
        frameloop="demand"
        dpr={[1, 2]}
        camera={{ position: [1.9, 1.35, 2.5], fov: BASE_FOV, near: 0.1, far: 50 }}
        aria-label="Rotatable 3D implied volatility surface"
      >
        <SceneContents geo={geo} labels={labels} els={els} />
      </Canvas>
      <div className="hero-labels" aria-hidden="true">
        {labels.map((l, i) => (
          <span
            key={`${l.title ? 'title' : 'tick'}-${i}`}
            ref={(el) => {
              els.current[i] = el
            }}
            className={l.title ? 'hero-axis hero-axis-title' : 'hero-axis'}
          >
            {l.text}
          </span>
        ))}
      </div>
    </>
  )
}

/** Catches a WebGL failure that detectWebGL() could not predict (context lost, driver crash). */
class SceneBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

/** What the hero draws: any grid of IVs, iv[i_dte][j_moneyness]; an IllustrativeSurface is one. */
export type SurfaceGrid = Pick<IllustrativeSurface, 'moneyness' | 'dte' | 'iv'>

function HeatmapFallback({ surface }: { surface: SurfaceGrid }) {
  return (
    <div className="hero-fallback">
      <p className="sub">3D view unavailable: this browser could not start WebGL. The same grid is shown as a heatmap instead.</p>
      <Heatmap rows={surface.iv} xLabels={surface.moneyness.map((k) => fmt(k, 2))} yLabels={surface.dte.map((d) => `${d}d`)} />
    </div>
  )
}

/**
 * `label` is the badge over the surface. It comes from the caller, never from the dataset, so the
 * illustrative hero keeps its "not market data" label whatever the file's own label says.
 */
export function SurfaceHero({
  surface,
  label = SURFACE_LABEL,
  webglAvailable = detectWebGL,
}: {
  surface: SurfaceGrid
  label?: string
  webglAvailable?: () => boolean
}) {
  const geo = useMemo(() => buildSurfaceGeometry(surface.moneyness, surface.dte, surface.iv), [surface])
  // Probed once per mount: creating a throwaway WebGL context on every render would be wasteful.
  const [hasWebGL] = useState(webglAvailable)
  const { moneyness, dte, iv } = geo.extent

  return (
    <figure className="hero">
      <span className="hero-label badge">{label}</span>
      <div className="hero-stage">
        {hasWebGL ? (
          <SceneBoundary fallback={<HeatmapFallback surface={surface} />}>
            <Scene3D geo={geo} />
          </SceneBoundary>
        ) : (
          <HeatmapFallback surface={surface} />
        )}
      </div>
      <figcaption className="hero-caption">
        <span>
          x: log-moneyness {fmt(moneyness[0], 2)} to {fmt(moneyness[1], 2)} · y and colour: implied vol {pct(iv[0], 1)} to {pct(iv[1], 1)} · z: days to
          expiry {dte[0]} to {dte[1]}
        </span>
        <span className="ramp-legend">
          <span>{pct(iv[0], 1)}</span>
          <span className="ramp-bar" style={{ background: `linear-gradient(to right, ${RAMP_STOPS.join(', ')})` }} role="presentation" />
          <span>{pct(iv[1], 1)}</span>
        </span>
        {hasWebGL && <span>Drag to rotate.</span>}
      </figcaption>
    </figure>
  )
}
