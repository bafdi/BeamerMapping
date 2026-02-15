"""GPU-beschleunigtes Compositing mit moderngl."""

import logging
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Vertex Shader: Full-screen quad
_VERTEX_SHADER = """
#version 330 core

in vec2 in_position;

void main() {
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

# Fragment Shader: Per-pixel inverse homography sampling
_FRAGMENT_SHADER = """
#version 330 core

uniform sampler2D source_tex;
uniform mat3 inv_homography;
uniform vec2 output_size;
uniform vec2 source_size;

// Polygon clip quad (output-space, normalized 0..1)
uniform vec4 clip_quad_01;  // (min_x, min_y, max_x, max_y) bounding box
uniform vec2 quad_p0;
uniform vec2 quad_p1;
uniform vec2 quad_p2;
uniform vec2 quad_p3;

out vec4 frag_color;

// Check if point is inside convex quad using cross-product winding
bool point_in_quad(vec2 p, vec2 a, vec2 b, vec2 c, vec2 d) {
    float d1 = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
    float d2 = (c.x - b.x) * (p.y - b.y) - (c.y - b.y) * (p.x - b.x);
    float d3 = (d.x - c.x) * (p.y - c.y) - (d.y - c.y) * (p.x - c.x);
    float d4 = (a.x - d.x) * (p.y - d.y) - (a.y - d.y) * (p.x - d.x);

    bool has_neg = (d1 < 0.0) || (d2 < 0.0) || (d3 < 0.0) || (d4 < 0.0);
    bool has_pos = (d1 > 0.0) || (d2 > 0.0) || (d3 > 0.0) || (d4 > 0.0);

    return !(has_neg && has_pos);
}

void main() {
    // Fragment position in output pixel space
    vec2 frag_px = gl_FragCoord.xy;
    // Flip Y: OpenGL origin is bottom-left, our images are top-left
    frag_px.y = output_size.y - frag_px.y;

    // Normalized output coords (0..1)
    vec2 frag_norm = frag_px / output_size;

    // Bounding box early-out
    if (frag_norm.x < clip_quad_01.x || frag_norm.x > clip_quad_01.z ||
        frag_norm.y < clip_quad_01.y || frag_norm.y > clip_quad_01.w) {
        discard;
    }

    // Polygon containment test
    if (!point_in_quad(frag_norm, quad_p0, quad_p1, quad_p2, quad_p3)) {
        discard;
    }

    // Apply inverse homography: output pixel -> source pixel
    vec3 src_h = inv_homography * vec3(frag_px, 1.0);
    vec2 src_px = src_h.xy / src_h.z;

    // Bounds check in source space
    if (src_px.x < 0.0 || src_px.x >= source_size.x ||
        src_px.y < 0.0 || src_px.y >= source_size.y) {
        discard;
    }

    // Sample source texture (normalized coords, flip Y back for texture)
    vec2 tex_coord = src_px / source_size;
    frag_color = texture(source_tex, tex_coord);
}
"""

# Mesh Vertex Shader: Bilinear mesh warping (Position + UV durchreichen)
_MESH_VERTEX_SHADER = """
#version 330 core

in vec2 in_position;
in vec2 in_texcoord;

out vec2 v_texcoord;

void main() {
    gl_Position = vec4(in_position, 0.0, 1.0);
    v_texcoord = in_texcoord;
}
"""

# Mesh Fragment Shader: Einfaches Texture-Sampling (GPU interpoliert UVs)
_MESH_FRAGMENT_SHADER = """
#version 330 core

uniform sampler2D source_tex;

in vec2 v_texcoord;
out vec4 frag_color;

void main() {
    frag_color = texture(source_tex, v_texcoord);
}
"""


class GLCompositor:
    """GPU-beschleunigtes Polygon-Compositing via moderngl."""

    def __init__(self):
        self._ctx = None
        self._prog = None
        self._vao = None
        self._fbo = None
        self._fbo_size = (0, 0)
        self._texture_cache = {}  # id(ndarray) -> (texture, shape)
        self._mesh_prog = None
        self._mesh_vbo = None
        self._mesh_ibo = None
        self._mesh_vao = None
        self._initialized = False
        self._init_failed = False

    def _ensure_init(self) -> bool:
        """Lazy-Init des OpenGL Kontexts. Returns True bei Erfolg."""
        if self._initialized:
            return True
        if self._init_failed:
            return False

        try:
            import moderngl
            self._ctx = moderngl.create_standalone_context(require=330)
            self._prog = self._ctx.program(
                vertex_shader=_VERTEX_SHADER,
                fragment_shader=_FRAGMENT_SHADER,
            )

            # Full-screen quad (-1..1)
            vertices = np.array([
                -1.0, -1.0,
                 1.0, -1.0,
                 1.0,  1.0,
                -1.0, -1.0,
                 1.0,  1.0,
                -1.0,  1.0,
            ], dtype='f4')

            vbo = self._ctx.buffer(vertices)
            self._vao = self._ctx.simple_vertex_array(self._prog, vbo, 'in_position')

            # Mesh-Shader fuer Bilinear Mesh Warping
            self._mesh_prog = self._ctx.program(
                vertex_shader=_MESH_VERTEX_SHADER,
                fragment_shader=_MESH_FRAGMENT_SHADER,
            )

            # Index Buffer fuer 20x20 Grid (konstant, 800 Dreiecke)
            grid_rows, grid_cols = 20, 20
            cols_plus1 = grid_cols + 1
            indices = []
            for r in range(grid_rows):
                for c in range(grid_cols):
                    tl = r * cols_plus1 + c
                    tr = r * cols_plus1 + (c + 1)
                    bl = (r + 1) * cols_plus1 + c
                    br = (r + 1) * cols_plus1 + (c + 1)
                    indices.extend([tl, tr, bl])
                    indices.extend([tr, br, bl])

            index_data = np.array(indices, dtype=np.int32)
            self._mesh_ibo = self._ctx.buffer(index_data)

            # Dynamischer VBO fuer Mesh-Vertices (441 Vertices × 4 floats)
            self._mesh_vbo = self._ctx.buffer(reserve=441 * 4 * 4)

            # VAO mit Index-Buffer
            self._mesh_vao = self._ctx.vertex_array(
                self._mesh_prog,
                [(self._mesh_vbo, '2f 2f', 'in_position', 'in_texcoord')],
                index_buffer=self._mesh_ibo,
                index_element_size=4,
            )

            self._initialized = True
            logger.info("OpenGL Compositor initialisiert (moderngl)")
            return True

        except Exception as e:
            logger.warning(f"OpenGL Compositor Init fehlgeschlagen: {e}")
            self._init_failed = True
            return False

    def _ensure_fbo(self, width: int, height: int):
        """Stelle sicher dass FBO die richtige Groesse hat."""
        if self._fbo_size == (width, height) and self._fbo is not None:
            return

        if self._fbo is not None:
            self._fbo.release()

        color_att = self._ctx.texture((width, height), 4)
        color_att.filter = (self._ctx.LINEAR, self._ctx.LINEAR)
        self._fbo = self._ctx.framebuffer(color_attachments=[color_att])
        self._fbo_size = (width, height)

    def _get_texture(self, image: np.ndarray):
        """Hole oder erstelle Textur fuer ein Bild."""
        import cv2

        arr_id = id(image)
        shape = image.shape

        if arr_id in self._texture_cache:
            tex, cached_shape = self._texture_cache[arr_id]
            if cached_shape == shape:
                # Textur existiert, Daten aktualisieren
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                tex.write(rgb.tobytes())
                return tex
            else:
                tex.release()

        # Neue Textur erstellen
        h, w = shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tex = self._ctx.texture((w, h), 3, rgb.tobytes())
        tex.filter = (self._ctx.LINEAR, self._ctx.LINEAR)

        # Cache begrenzen
        if len(self._texture_cache) > 32:
            oldest_key = next(iter(self._texture_cache))
            self._texture_cache[oldest_key][0].release()
            del self._texture_cache[oldest_key]

        self._texture_cache[arr_id] = (tex, shape)
        return tex

    def _generate_mesh_vertices(
        self,
        source_points: list,
        output_points: list,
    ) -> np.ndarray:
        """Generiere Mesh-Vertices fuer bilineares Grid-Warping auf der GPU.

        Returns: np.ndarray shape (441, 4) dtype float32 — [ndc_x, ndc_y, uv_x, uv_y]
        """
        grid_rows, grid_cols = 20, 20

        p0_s = np.array(source_points[0])
        p1_s = np.array(source_points[1])
        p2_s = np.array(source_points[2])
        p3_s = np.array(source_points[3])

        p0_o = np.array(output_points[0])
        p1_o = np.array(output_points[1])
        p2_o = np.array(output_points[2])
        p3_o = np.array(output_points[3])

        ug = np.linspace(0, 1, grid_cols + 1)
        vg = np.linspace(0, 1, grid_rows + 1)
        u, v = np.meshgrid(ug, vg)

        # Bilineare Interpolationsgewichte
        w00 = (1 - u) * (1 - v)
        w10 = u * (1 - v)
        w11 = u * v
        w01 = (1 - u) * v

        # Source Grid → UV-Koordinaten
        src_grid = (w00[..., np.newaxis] * p0_s +
                    w10[..., np.newaxis] * p1_s +
                    w11[..., np.newaxis] * p2_s +
                    w01[..., np.newaxis] * p3_s)

        # Output Grid → NDC-Koordinaten
        out_grid = (w00[..., np.newaxis] * p0_o +
                    w10[..., np.newaxis] * p1_o +
                    w11[..., np.newaxis] * p2_o +
                    w01[..., np.newaxis] * p3_o)

        # Output → NDC: x*2-1, (1-y)*2-1
        ndc_x = out_grid[..., 0] * 2.0 - 1.0
        ndc_y = (1.0 - out_grid[..., 1]) * 2.0 - 1.0

        # Source → UV: direkt (Textur-Row 0 = erster Upload-Row = Bild-Top bei v=0)
        uv_x = src_grid[..., 0]
        uv_y = src_grid[..., 1]

        # Interleaved Array: [ndc_x, ndc_y, uv_x, uv_y]
        n_verts = (grid_rows + 1) * (grid_cols + 1)
        vertices = np.empty((n_verts, 4), dtype=np.float32)
        vertices[:, 0] = ndc_x.ravel()
        vertices[:, 1] = ndc_y.ravel()
        vertices[:, 2] = uv_x.ravel()
        vertices[:, 3] = uv_y.ravel()

        return vertices

    def composite(
        self,
        polygons_data: List[Tuple[np.ndarray, list, list]],
        output_size: Tuple[int, int],
        result_buffer: Optional[np.ndarray] = None,
        warp_method: str = "perspective"
    ) -> Optional[np.ndarray]:
        """
        Compositing via GPU.

        warp_method: 'perspective' (Homographie-Shader) oder 'bilinear_mesh' (Mesh-Rasterisierung).
        Returns None bei Fehler (Caller soll auf OpenCV fallback machen).
        """
        if not self._ensure_init():
            return None

        try:
            import cv2

            out_w, out_h = output_size

            self._ensure_fbo(out_w, out_h)
            self._fbo.use()
            self._ctx.clear(0.0, 0.0, 0.0, 1.0)
            self._ctx.enable(self._ctx.BLEND)
            self._ctx.blend_func = (self._ctx.SRC_ALPHA, self._ctx.ONE_MINUS_SRC_ALPHA)

            for image, source_points, output_points in polygons_data:
                if image is None or len(source_points) != 4 or len(output_points) != 4:
                    continue

                # Textur vorbereiten
                tex = self._get_texture(image)
                tex.use(0)

                if warp_method == "bilinear_mesh":
                    # Mesh-Vertices generieren und in VBO schreiben
                    vertices = self._generate_mesh_vertices(source_points, output_points)
                    self._mesh_vbo.write(vertices.tobytes())
                    self._mesh_prog['source_tex'].value = 0
                    self._mesh_vao.render()
                else:
                    # Perspective: Homographie-basiertes Rendering
                    img_h, img_w = image.shape[:2]

                    src_pts = np.array([
                        [source_points[i][0] * img_w, source_points[i][1] * img_h]
                        for i in range(4)
                    ], dtype=np.float32)

                    dst_pts = np.array([
                        [output_points[i][0] * out_w, output_points[i][1] * out_h]
                        for i in range(4)
                    ], dtype=np.float32)

                    H = cv2.getPerspectiveTransform(dst_pts, src_pts)

                    self._prog['source_tex'].value = 0
                    self._prog['output_size'].value = (float(out_w), float(out_h))
                    self._prog['source_size'].value = (float(img_w), float(img_h))

                    inv_h = H.astype(np.float32)
                    self._prog['inv_homography'].value = tuple(inv_h.T.flatten())

                    out_norms = [[output_points[i][0], output_points[i][1]] for i in range(4)]
                    min_x = max(0.0, min(p[0] for p in out_norms))
                    min_y = max(0.0, min(p[1] for p in out_norms))
                    max_x = min(1.0, max(p[0] for p in out_norms))
                    max_y = min(1.0, max(p[1] for p in out_norms))
                    self._prog['clip_quad_01'].value = (min_x, min_y, max_x, max_y)

                    self._prog['quad_p0'].value = tuple(out_norms[0])
                    self._prog['quad_p1'].value = tuple(out_norms[1])
                    self._prog['quad_p2'].value = tuple(out_norms[2])
                    self._prog['quad_p3'].value = tuple(out_norms[3])

                    self._vao.render()

            # FBO auslesen
            raw = self._fbo.color_attachments[0].read()
            result = np.frombuffer(raw, dtype=np.uint8).reshape((out_h, out_w, 4))
            # RGBA -> BGR, flip Y (OpenGL bottom-left origin)
            result_bgr = cv2.cvtColor(np.flipud(result), cv2.COLOR_RGBA2BGR)

            # In result_buffer kopieren falls vorhanden
            if result_buffer is not None and result_buffer.shape == (out_h, out_w, 3):
                np.copyto(result_buffer, result_bgr)
                return result_buffer

            return result_bgr.copy()

        except Exception as e:
            logger.warning(f"OpenGL Compositing fehlgeschlagen: {e}")
            return None

    def cleanup(self):
        """Ressourcen freigeben."""
        if self._ctx:
            for tex, _ in self._texture_cache.values():
                tex.release()
            self._texture_cache.clear()
            if self._mesh_vbo:
                self._mesh_vbo.release()
            if self._mesh_ibo:
                self._mesh_ibo.release()
            if self._fbo:
                self._fbo.release()
            self._ctx.release()
            self._ctx = None
            self._initialized = False
