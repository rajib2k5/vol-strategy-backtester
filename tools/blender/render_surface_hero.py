r"""Render a hero image of an implied-vol surface with Blender.

Run it with Blender's own Python, from the repo root:

    blender --background --python tools/blender/render_surface_hero.py -- \
        --data app/public/data/illustrative_surface.json \
        --out docs/images/blender/surface_hero.png

Everything after the lone `--` belongs to this script; Blender ignores it.

The file is split on purpose. The top half is plain Python (JSON checks, the
grid -> vertices/faces/colours maths, camera maths) and never imports bpy, so
an ordinary interpreter can import and test it. `bpy` is imported only inside
the Blender-side functions further down, and those need a real Blender.

Input is the app's surface JSON: moneyness (log-moneyness k), dte, and
iv[i_dte][j_k] as a decimal. Axes: x = k, y = DTE, z = IV.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = REPO_ROOT / "app" / "public" / "data" / "illustrative_surface.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "images" / "blender" / "surface_hero.png"
DEFAULT_SAMPLES = 64
DEFAULT_RESOLUTION = "1920x1080"
MAX_SIDE_PX = 16384

REQUIRED_KEYS = ("moneyness", "dte", "iv")
FALLBACK_LABEL = "Illustrative SSVI surface — not market data"

# The mesh is built in a unit box (each axis 0..1), then scaled by this for
# display. IV only spans a few vol points, so z is stretched to read as a shape.
DISPLAY_SIZE = (4.0, 4.0, 1.8)
COLOR_ATTRIBUTE = "iv_color"

# Camera: azimuth 0 looks along +y from the front; positive swings it to +x.
CAMERA_AZIMUTH_DEG = 38.0
CAMERA_ELEVATION_DEG = 30.0
CAMERA_LENS_MM = 50.0
CAMERA_SENSOR_MM = 36.0
# Content fills at most 1/FRAME_MARGIN of the frame, leaving room for the caption.
FRAME_MARGIN = 1.25
CAPTION_DISTANCE = 10.0

# Three-point rig as suns (strength is W/m2, so it does not depend on distance).
# name, azimuth, elevation (same convention as the camera), strength, angle (deg;
# a bigger angle gives softer shadows).
LIGHT_RIG = (
    ("key", -15.0, 50.0, 3.5, 4.0),
    ("fill", 85.0, 25.0, 1.0, 10.0),
    ("rim", 200.0, 35.0, 2.5, 3.0),
)

BACKGROUND_RGB = (0.015, 0.018, 0.025)
LABEL_RGB = (0.92, 0.93, 0.95)
WIRE_RGB = (0.85, 0.87, 0.90)
WIRE_THICKNESS = 0.008
# Tried in this order only if the engine enum read at runtime does not list them.
ENGINE_FALLBACKS = ("CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE")

# viridis sampled every 1/32 from matplotlib 3.11.0 (Blender ships no matplotlib).
# Linear interpolation between these stops is within 0.011 per channel of the
# 256-entry map. Perceptually uniform, so equal IV steps look like equal colour steps.
_VIRIDIS = (
    (0.2670, 0.0049, 0.3294), (0.2770, 0.0503, 0.3757), (0.2823, 0.0950, 0.4173),
    (0.2829, 0.1359, 0.4534), (0.2788, 0.1755, 0.4834), (0.2706, 0.2141, 0.5071),
    (0.2590, 0.2515, 0.5247), (0.2450, 0.2877, 0.5373), (0.2297, 0.3224, 0.5457),
    (0.2143, 0.3556, 0.5512), (0.1994, 0.3876, 0.5546), (0.1856, 0.4186, 0.5568),
    (0.1727, 0.4488, 0.5579), (0.1607, 0.4785, 0.5581), (0.1490, 0.5081, 0.5573),
    (0.1378, 0.5375, 0.5549), (0.1276, 0.5669, 0.5506), (0.1206, 0.5964, 0.5436),
    (0.1206, 0.6258, 0.5335), (0.1323, 0.6550, 0.5197), (0.1579, 0.6838, 0.5017),
    (0.1966, 0.7118, 0.4792), (0.2461, 0.7389, 0.4520), (0.3041, 0.7647, 0.4199),
    (0.3692, 0.7889, 0.3829), (0.4401, 0.8111, 0.3410), (0.5160, 0.8312, 0.2943),
    (0.5958, 0.8487, 0.2433), (0.6785, 0.8637, 0.1895), (0.7624, 0.8764, 0.1371),
    (0.8456, 0.8873, 0.0997), (0.9261, 0.8973, 0.1041), (0.9932, 0.9062, 0.1439),
)


# --------------------------------------------------------------------------- #
# Pure Python half: no bpy anywhere above the "Blender side" banner.
# --------------------------------------------------------------------------- #


def _is_number(value) -> bool:
    # bool is an int subclass, and JSON `true` in an IV grid is a bug, not a 1.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_axis(name: str, values) -> None:
    if not isinstance(values, list) or len(values) < 2:
        raise ValueError(f"'{name}' must be a list of at least 2 numbers")
    if not all(_is_number(v) for v in values):
        raise ValueError(f"'{name}' must contain only finite numbers")
    # Strictly increasing keeps every quad non-degenerate and the faces wound the same way.
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError(f"'{name}' must be strictly increasing")


def validate_surface(data) -> None:
    """Raise ValueError unless `data` has the keys and rectangular grid the mesh needs."""
    if not isinstance(data, dict):
        raise ValueError("surface JSON must be an object at the top level")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"surface JSON is missing key(s): {', '.join(missing)}")
    _check_axis("moneyness", data["moneyness"])
    _check_axis("dte", data["dte"])
    n_k, n_dte = len(data["moneyness"]), len(data["dte"])
    iv = data["iv"]
    # A transposed grid (one row per strike) is the likeliest export bug, so say which way it is.
    if not isinstance(iv, list) or len(iv) != n_dte:
        got = len(iv) if isinstance(iv, list) else type(iv).__name__
        raise ValueError(f"'iv' needs one row per dte ({n_dte}), got {got}; layout is iv[i_dte][j_k]")
    for i, row in enumerate(iv):
        if not isinstance(row, list) or len(row) != n_k:
            got = len(row) if isinstance(row, list) else type(row).__name__
            raise ValueError(f"'iv' row {i} needs one value per moneyness ({n_k}), got {got}")
        if not all(_is_number(v) for v in row):
            raise ValueError(f"'iv' row {i} must contain only finite numbers")


def normalise(values) -> list[float]:
    """Map min -> 0.0 and max -> 1.0 linearly. A constant input maps to all zeros."""
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0:
        return [0.0] * len(values)
    return [(v - lo) / span for v in values]


def viridis(t: float) -> tuple[float, float, float]:
    """sRGB colour for t in 0..1 (clamped), interpolated between the _VIRIDIS stops."""
    t = min(max(t, 0.0), 1.0)
    pos = t * (len(_VIRIDIS) - 1)
    i = min(int(pos), len(_VIRIDIS) - 2)
    frac = pos - i
    a, b = _VIRIDIS[i], _VIRIDIS[i + 1]
    return (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac, a[2] + (b[2] - a[2]) * frac)


def srgb_to_linear(c: float) -> float:
    """Blender does its lighting maths in linear light, but viridis stops are sRGB."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


class SurfaceMesh(NamedTuple):
    # A NamedTuple, not a dataclass: dataclasses look the module up in sys.modules, which
    # breaks when a test imports this file by path (tools/ is not a package).
    # Vertex index is i_dte * n_k + j_k, matching iv[i_dte][j_k] read row by row.
    vertices: list[tuple[float, float, float]]
    faces: list[tuple[int, int, int, int]]
    colors: list[tuple[float, float, float, float]]  # sRGB RGBA, one per vertex
    n_k: int
    n_dte: int
    k_range: tuple[float, float]
    dte_range: tuple[float, float]
    iv_range: tuple[float, float]
    size: tuple[float, float, float]


def build_surface_mesh(data: dict, size: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> SurfaceMesh:
    """Turn the surface JSON into quads in a box of `size` (default: the unit box).

    x = k, y = DTE, z = IV, each normalised so its min is 0 and its max is `size`.
    Colour follows the normalised IV, so the ramp spans the surface's own range.
    """
    validate_surface(data)
    ks = [float(v) for v in data["moneyness"]]
    dtes = [float(v) for v in data["dte"]]
    iv = [[float(v) for v in row] for row in data["iv"]]
    n_k, n_dte = len(ks), len(dtes)

    xs, ys = normalise(ks), normalise(dtes)
    zs = normalise([v for row in iv for v in row])
    sx, sy, sz = size

    vertices, colors = [], []
    for i in range(n_dte):
        for j in range(n_k):
            z = zs[i * n_k + j]
            vertices.append((xs[j] * sx, ys[i] * sy, z * sz))
            r, g, b = viridis(z)
            colors.append((r, g, b, 1.0))

    # Counter-clockwise seen from +z, so every face normal points up at the camera.
    faces = [
        (i * n_k + j, i * n_k + j + 1, (i + 1) * n_k + j + 1, (i + 1) * n_k + j)
        for i in range(n_dte - 1)
        for j in range(n_k - 1)
    ]
    iv_flat = [v for row in iv for v in row]
    return SurfaceMesh(
        vertices=vertices,
        faces=faces,
        colors=colors,
        n_k=n_k,
        n_dte=n_dte,
        k_range=(ks[0], ks[-1]),
        dte_range=(dtes[0], dtes[-1]),
        iv_range=(min(iv_flat), max(iv_flat)),
        size=tuple(size),
    )


def surface_label(data: dict) -> str:
    """Caption text: the file's own label, else the illustrative one only if the file says it is."""
    label = data.get("label")
    if isinstance(label, str) and label.strip():
        return label
    # Never guess: stamping "illustrative" on real data (or the reverse) would mislead.
    if data.get("illustrative") is True:
        return FALLBACK_LABEL
    raise ValueError("surface JSON has no 'label' and is not marked illustrative; cannot caption it")


class Annotation(NamedTuple):
    text: str
    position: tuple[float, float, float]
    kind: str  # "title" or "tick"


def axis_annotations(surface: SurfaceMesh) -> list[Annotation]:
    """Axis titles plus min/max tick text, placed just outside the box edges.

    Without the end values the picture shows a shape but not what it is a shape of.
    """
    sx, sy, sz = surface.size
    tick, title = 0.08 * sx, 0.22 * sx
    k0, k1 = surface.k_range
    d0, d1 = surface.dte_range
    v0, v1 = surface.iv_range
    return [
        Annotation("log-moneyness k", (sx / 2, -title, 0.0), "title"),
        Annotation(f"{k0:+.2f}", (0.0, -tick, 0.0), "tick"),
        Annotation(f"{k1:+.2f}", (sx, -tick, 0.0), "tick"),
        Annotation("days to expiry", (sx + title, sy / 2, 0.0), "title"),
        Annotation(f"{d0:g}d", (sx + tick, 0.0, 0.0), "tick"),
        Annotation(f"{d1:g}d", (sx + tick, sy, 0.0), "tick"),
        Annotation("implied vol", (-title, 0.0, sz / 2), "title"),
        Annotation(f"{v0 * 100:.1f}%", (-tick, 0.0, 0.0), "tick"),
        Annotation(f"{v1 * 100:.1f}%", (-tick, 0.0, sz), "tick"),
    ]


# ----- camera and light maths (pure so the framing can be checked without Blender) -----


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v):
    n = math.sqrt(_dot(v, v))
    return (v[0] / n, v[1] / n, v[2] / n)


def direction_from_angles(azimuth_deg: float, elevation_deg: float) -> tuple[float, float, float]:
    """Unit vector from the scene centre out towards a camera or light."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    return (math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el))


def look_at_euler(forward) -> tuple[float, float, float]:
    """Blender XYZ Euler for a camera/light whose -Z axis points along `forward`, +Y up-ish.

    Written out by hand so the Blender side needs no mathutils. Blender cameras
    look down their local -Z; rx tilts that off straight-down, rz turns it about world Z.
    """
    fx, fy, fz = _unit(forward)
    return (math.acos(max(-1.0, min(1.0, -fz))), 0.0, math.atan2(-fx, fy))


def camera_fov(lens_mm: float, sensor_width_mm: float, aspect: float) -> tuple[float, float]:
    """(horizontal, vertical) field of view in radians, with the sensor fitted to the width."""
    hfov = 2 * math.atan(sensor_width_mm / (2 * lens_mm))
    return hfov, 2 * math.atan(math.tan(hfov / 2) / aspect)


def box_corners(size) -> list[tuple[float, float, float]]:
    return [(x * size[0], y * size[1], z * size[2]) for x, y, z in itertools.product((0, 1), repeat=3)]


def fit_camera_distance(points, target, direction, hfov, vfov, margin=FRAME_MARGIN) -> float:
    """Smallest distance (to within 2%) from `target` along `direction` that frames every point.

    A point fits when its tangent off the view axis, times `margin`, stays inside the
    field of view. Fitting by projecting real points beats guessing a distance, because
    a wrong guess crops the plot and nobody sees that until the render has run.
    """
    forward = tuple(-c for c in direction)
    right = _cross(forward, (0.0, 0.0, 1.0))
    # Looking straight down has no "right" from world-up; any horizontal axis will do.
    right = _unit(right) if _dot(right, right) > 1e-12 else (1.0, 0.0, 0.0)
    up = _cross(right, forward)
    tan_h, tan_v = math.tan(hfov / 2), math.tan(vfov / 2)

    def fits(dist: float) -> bool:
        cam = tuple(t + d * dist for t, d in zip(target, direction))
        for p in points:
            v = (p[0] - cam[0], p[1] - cam[1], p[2] - cam[2])
            depth = _dot(v, forward)
            if depth <= 0:
                return False
            if abs(_dot(v, right)) / depth * margin > tan_h or abs(_dot(v, up)) / depth * margin > tan_v:
                return False
        return True

    dist = 1.0
    for _ in range(2000):
        if fits(dist):
            return dist
        dist *= 1.02
    raise ValueError("could not frame the scene at any camera distance")


def engine_candidates(available) -> list[str]:
    """Render engines to try in order: Cycles, then any EEVEE flavour, then known names.

    EEVEE's identifier changed between Blender versions (BLENDER_EEVEE,
    BLENDER_EEVEE_NEXT), so match on "EEVEE" in what this Blender reports.

    Cycles goes first even if `available` does not list it: the enum under-reports (Cycles is
    an add-on), and the caller assigns each candidate inside try/except TypeError, so an engine
    that really is missing costs one failed assignment and the next one is tried.
    """
    order = ["CYCLES"]
    # Reverse sort puts BLENDER_EEVEE_NEXT ahead of BLENDER_EEVEE when both exist.
    order += sorted((e for e in available if "EEVEE" in e), reverse=True)
    order += [e for e in ENGINE_FALLBACKS if e not in order]
    return order


# ----- command line -----


def script_args(argv) -> list[str]:
    """The part of argv after the first `--`; Blender keeps its own flags before it."""
    return list(argv[argv.index("--") + 1 :]) if "--" in argv else []


def parse_resolution(text: str) -> tuple[int, int]:
    """'1920x1080' -> (1920, 1080)."""
    try:
        width_text, height_text = text.lower().split("x")
        width, height = int(width_text), int(height_text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"resolution must look like 1920x1080, got {text!r}") from None
    if not (1 <= width <= MAX_SIDE_PX and 1 <= height <= MAX_SIDE_PX):
        raise argparse.ArgumentTypeError(f"resolution sides must be 1..{MAX_SIDE_PX}, got {text!r}")
    return width, height


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a whole number, got {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def _png_path(text: str) -> Path:
    path = Path(text)
    # Only PNG is wired up, and a missing suffix would leave Blender guessing the name.
    if path.suffix.lower() != ".png":
        raise argparse.ArgumentTypeError(f"--out must end in .png, got {text!r}")
    return path


def parse_args(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="blender --background --python tools/blender/render_surface_hero.py --",
        description="Render a 3D hero image of an implied-vol surface JSON.",
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="surface JSON (default: %(default)s)")
    parser.add_argument("--out", type=_png_path, default=DEFAULT_OUT, help="output PNG (default: %(default)s)")
    parser.add_argument(
        "--samples", type=_positive_int, default=DEFAULT_SAMPLES, help="render samples (default: %(default)s)"
    )
    parser.add_argument(
        "--resolution",
        type=parse_resolution,
        default=parse_resolution(DEFAULT_RESOLUTION),
        metavar="WxH",
        help=f"image size (default: {DEFAULT_RESOLUTION})",
    )
    return parser.parse_args(args)


def load_surface(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_surface(data)
    return data


# --------------------------------------------------------------------------- #
# Blender side: every function below imports bpy itself, so importing this
# module in a normal Python never touches it. None of this has run yet.
# --------------------------------------------------------------------------- #


def clear_scene() -> None:
    """Empty the startup scene (cube, light, camera) so only our objects get rendered."""
    import bpy

    # The data API instead of bpy.ops.object.delete: ops need a UI context, and --background has none.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for block_set in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.curves):
        for block in list(block_set):
            block_set.remove(block)


def configure_render(scene, out: Path, samples: int, resolution: tuple[int, int]) -> str:
    """Pick the engine, set samples, size and PNG output. Returns the engine used."""
    import bpy

    # Enum identifiers differ between Blender versions, so read what this one offers.
    available = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    last_error = None
    for engine in engine_candidates(available):
        try:
            scene.render.engine = engine
            break
        except TypeError as exc:  # engine unknown or its add-on disabled; the message lists valid ones
            last_error = exc
    else:
        raise RuntimeError(f"no usable render engine (tried {engine_candidates(available)}): {last_error}")

    if engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True  # few samples + denoise is much cheaper than many samples
    else:
        scene.eevee.taa_render_samples = samples

    formats = [i.identifier for i in bpy.types.ImageFormatSettings.bl_rna.properties["file_format"].enum_items]
    if "PNG" not in formats:
        raise RuntimeError(f"this Blender has no PNG output; it offers {formats}")
    scene.render.image_settings.file_format = "PNG"
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out.resolve())
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100

    # Blender 4 defaults to AgX, which desaturates; Standard keeps viridis true to the ramp.
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass  # keep whatever this version defaults to
    return engine


def _node_by_type(tree, node_type: str, bl_idname: str):
    # Look nodes up by .type, never by name: node names are localised.
    node = next((n for n in tree.nodes if n.type == node_type), None)
    return node if node is not None else tree.nodes.new(bl_idname)


def _vertex_color_material(name: str):
    import bpy

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = _node_by_type(tree, "BSDF_PRINCIPLED", "ShaderNodeBsdfPrincipled")
    output = _node_by_type(tree, "OUTPUT_MATERIAL", "ShaderNodeOutputMaterial")
    if not bsdf.outputs["BSDF"].is_linked:
        tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    color = tree.nodes.new("ShaderNodeVertexColor")
    color.layer_name = COLOR_ATTRIBUTE
    tree.links.new(color.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def _emission_material(name: str, rgb, strength: float):
    """Flat self-lit colour: labels and wire stay crisp whatever the lights do."""
    import bpy

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*rgb, 1.0)
    emission.inputs["Strength"].default_value = strength
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def set_background(scene) -> None:
    import bpy

    world = bpy.data.worlds.new("hero_world")
    world.use_nodes = True
    background = _node_by_type(world.node_tree, "BACKGROUND", "ShaderNodeBackground")
    background.inputs["Color"].default_value = (*BACKGROUND_RGB, 1.0)
    background.inputs["Strength"].default_value = 1.0
    scene.world = world


def add_surface(scene, surface: SurfaceMesh) -> None:
    """The coloured, smooth-shaded surface plus a thin wireframe copy on top."""
    import bpy

    mesh = bpy.data.meshes.new("surface_mesh")
    mesh.from_pydata(surface.vertices, [], surface.faces)  # no explicit edges: Blender derives them
    mesh.update()
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))

    # One colour per vertex, stored in linear light because Blender's shader maths is linear.
    attr = mesh.color_attributes.new(name=COLOR_ATTRIBUTE, type="FLOAT_COLOR", domain="POINT")
    flat = [srgb_to_linear(c) if idx < 3 else c for rgba in surface.colors for idx, c in enumerate(rgba)]
    attr.data.foreach_set("color", flat)

    mesh.materials.append(_vertex_color_material("surface_vertex_colors"))
    obj = bpy.data.objects.new("surface", mesh)
    scene.collection.objects.link(obj)

    # A separate mesh copy so the wire has its own material slot. The wireframe modifier
    # replaces faces with thin strips; offset=1 lifts them onto the surface, not into it.
    wire_mesh = mesh.copy()
    wire_mesh.materials.clear()
    wire_mesh.materials.append(_emission_material("surface_wire", WIRE_RGB, 0.6))
    wire = bpy.data.objects.new("surface_wire", wire_mesh)
    modifier = wire.modifiers.new("wireframe", "WIREFRAME")
    modifier.thickness = WIRE_THICKNESS
    modifier.offset = 1.0
    modifier.use_replace = True
    modifier.use_even_offset = True
    scene.collection.objects.link(wire)


def add_camera(scene, surface: SurfaceMesh, resolution: tuple[int, int]):
    """3/4-view camera whose distance is fitted so the box and its labels fill the frame."""
    import bpy

    cam_data = bpy.data.cameras.new("hero_camera")
    cam_data.lens = CAMERA_LENS_MM
    cam_data.sensor_width = CAMERA_SENSOR_MM
    # Fit the sensor to the width so the field of view matches camera_fov() below.
    cam_data.sensor_fit = "HORIZONTAL"

    target = tuple(s / 2 for s in surface.size)
    direction = direction_from_angles(CAMERA_AZIMUTH_DEG, CAMERA_ELEVATION_DEG)
    hfov, vfov = camera_fov(CAMERA_LENS_MM, CAMERA_SENSOR_MM, resolution[0] / resolution[1])
    points = box_corners(surface.size) + [a.position for a in axis_annotations(surface)]
    dist = fit_camera_distance(points, target, direction, hfov, vfov)
    cam_data.clip_end = dist * 4

    cam = bpy.data.objects.new("hero_camera", cam_data)
    cam.location = tuple(t + d * dist for t, d in zip(target, direction))
    cam.rotation_euler = look_at_euler(tuple(-d for d in direction))
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam, hfov, vfov


def _add_text(scene, name: str, body: str, location, size: float, material, rotation, parent=None):
    import bpy

    curve = bpy.data.curves.new(name=name, type="FONT")
    curve.body = body
    curve.size = size
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.materials.append(material)
    obj = bpy.data.objects.new(name, curve)
    obj.location = location
    obj.rotation_euler = rotation
    if parent is not None:
        obj.parent = parent
    scene.collection.objects.link(obj)
    return obj


def add_labels(scene, surface: SurfaceMesh, cam, hfov: float, vfov: float, label: str) -> None:
    """Axis text and the caption. All of it turns to face the camera so it stays readable."""
    material = _emission_material("label_text", LABEL_RGB, 1.0)
    sizes = {"title": 0.075 * surface.size[0], "tick": 0.055 * surface.size[0]}
    # The camera never moves, so copying its rotation once is enough to billboard the text.
    facing = tuple(cam.rotation_euler)
    for idx, note in enumerate(axis_annotations(surface)):
        _add_text(scene, f"axis_{idx}", note.text, note.position, sizes[note.kind], material, facing)

    # The caption is parented to the camera so it sits at a fixed spot in the frame
    # whatever the fitted distance turns out to be.
    half_h = CAPTION_DISTANCE * math.tan(vfov / 2)
    half_w = CAPTION_DISTANCE * math.tan(hfov / 2)
    # Cap the size by width too (about 0.62 em per character), so a long label never overflows.
    size = min(0.075 * half_h, 0.85 * 2 * half_w / (0.62 * len(label)))
    _add_text(scene, "caption", label, (0.0, 0.9 * half_h, -CAPTION_DISTANCE), size, material, (0.0, 0.0, 0.0), parent=cam)


def add_lights(scene, target) -> None:
    """Key / fill / rim. Key models the shape, fill lifts the shadows, rim separates it from the background."""
    import bpy

    for name, azimuth, elevation, strength, angle in LIGHT_RIG:
        direction = direction_from_angles(azimuth, elevation)
        light = bpy.data.lights.new(name=name, type="SUN")
        light.energy = strength
        light.angle = math.radians(angle)
        obj = bpy.data.objects.new(name, light)
        # A sun lights along its local -Z, so aim that at the target; its position is irrelevant.
        obj.rotation_euler = look_at_euler(tuple(-d for d in direction))
        obj.location = tuple(t + d * 10 for t, d in zip(target, direction))
        scene.collection.objects.link(obj)


def render_hero(surface: SurfaceMesh, label: str, out: Path, samples: int, resolution: tuple[int, int]) -> None:
    import bpy

    clear_scene()
    scene = bpy.context.scene
    engine = configure_render(scene, out, samples, resolution)
    set_background(scene)
    add_surface(scene, surface)
    cam, hfov, vfov = add_camera(scene, surface, resolution)
    add_labels(scene, surface, cam, hfov, vfov, label)
    add_lights(scene, tuple(s / 2 for s in surface.size))
    print(f"render_surface_hero: engine={engine} samples={samples} size={resolution[0]}x{resolution[1]} -> {out}")
    bpy.ops.render.render(write_still=True)


def main(argv=None) -> None:
    args = parse_args(script_args(sys.argv if argv is None else argv))
    data = load_surface(args.data)
    surface = build_surface_mesh(data, size=DISPLAY_SIZE)
    label = surface_label(data)
    print(
        f"render_surface_hero: {args.data} schema_version={data.get('schema_version')} "
        f"source_commit={data.get('source_commit')} grid={surface.n_dte} dte x {surface.n_k} k "
        f"({len(surface.vertices)} vertices, {len(surface.faces)} quads)"
    )
    render_hero(surface, label, args.out, args.samples, args.resolution)


if __name__ == "__main__":
    main()
