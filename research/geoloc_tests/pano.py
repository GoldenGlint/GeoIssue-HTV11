"""Equirectangular (Mapillary 360) panorama -> perspective views, and the heading of each view.

Coordinate frames (all right-handed)
-----------------------------------
P  pano frame = OpenSfM "spherical" camera, which Mapillary uses for every 360 image:
   x right, y down, z forward.  z points at the CENTRE COLUMN of the equirect image on the
   horizon row.  Pixel column u (0..W-1, pixel centres on integers) has longitude
   lon = (u + 0.5) / W * 360 - 180 deg (lon > 0 = to the right of centre), row v has latitude
   lat = 90 - (v + 0.5) / H * 180 deg (lat > 0 = above the horizon).  Unit ray:
   [cos(lat) sin(lon), -sin(lat), cos(lat) cos(lon)].
C  virtual pinhole camera = OpenCV: x right, y down, z = optical axis.  Pixel centres on
   integers, principal point ((w - 1) / 2, (h - 1) / 2), square pixels.
W  world = Mapillary/OpenSfM local topocentric frame at the image: x east, y north, z up.

Mapillary convention (checked against the API and empirically, see `--verify-heading`)
-----------------------------------------------------------------------------------
* `computed_rotation` is an axis-angle vector r with  X_P = Rodrigues(r) @ X_W
  (world -> pano camera; translation omitted, the pano sits at `computed_geometry`).
* `computed_compass_angle` is the compass heading of the pano's +z axis, i.e. of the centre
  column: heading(z_P) = atan2(R[2,0], R[2,1]) with R = Rodrigues(r).  This holds exactly for
  every image checked.  `compass_angle` is the raw device value for the same column.
* Heading increases to the right in the image (column u -> heading + lon(u)).

Levelling: Mapillary 360 frames are often NOT gravity-aligned (helmet / roof-rack cameras; the
SfM tilt of the pano z/y axes is 9 deg median, 18 deg at the 90th percentile in our harvest), so a
plain pitch-0 view has a sloping horizon.  `level_rotation(meta)` gives R_level_from_pano: a frame
L with the same compass heading as the pano's centre column but y_L = straight down.

`perspective(img, yaw, pitch, fov, w, h, level=None)` returns R = R_cam_from_pano
(X_C = R @ X_P).  yaw > 0 turns right (clockwise seen from above), pitch > 0 looks up, no roll,
measured in the pano frame, or in the levelled frame when `level` is given (then
R = view_rotation(yaw, pitch) @ level).  Either way the virtual camera's world rotation is
    R_cam_from_world = R @ Rodrigues(computed_rotation)
and its camera centre is the pano's computed_geometry.  Its compass heading is
`absolute_heading(meta, yaw, pitch, leveled=level is not None)`; for a levelled view that is
exactly computed_compass_angle + yaw.

Self-test:  .venv/Scripts/python pano.py [--pano <id>] [--verify-heading]
"""
import argparse
import json
import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent


def rot_y(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])


def rot_x(deg):
    a = math.radians(deg)
    return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])


def view_rotation(yaw_deg, pitch_deg=0.0):
    """R_cam_from_pano for a virtual camera turned yaw_deg right and pitch_deg up (no roll)."""
    # camera -> pano: first pitch about the camera x axis, then yaw about the pano's (down) y axis.
    # rot_x(+a) maps [0,0,1] to [0,-sin a,cos a] = up (y is down); rot_y(+a) maps it to the right.
    return (rot_y(yaw_deg) @ rot_x(pitch_deg)).T


def intrinsics(fov_deg, out_w, out_h):
    """3x3 K for a horizontal field of view fov_deg; square pixels, centred principal point."""
    f = (out_w / 2) / math.tan(math.radians(fov_deg) / 2)
    return np.array([[f, 0, (out_w - 1) / 2], [0, f, (out_h - 1) / 2], [0, 0, 1.0]])


@lru_cache(maxsize=16)
def _camera_rays(fov_deg, out_w, out_h):
    K = intrinsics(fov_deg, out_w, out_h)
    xs, ys = np.meshgrid(np.arange(out_w, dtype=np.float32), np.arange(out_h, dtype=np.float32))
    rays = np.stack([(xs - K[0, 2]) / K[0, 0], (ys - K[1, 2]) / K[1, 1], np.ones_like(xs)], -1)
    return rays.astype(np.float32), K


def _maps(pano_w, pano_h, R, fov_deg, out_w, out_h):
    rays, K = _camera_rays(fov_deg, out_w, out_h)
    rays = rays @ R.astype(np.float32)  # row-vector form of R.T @ ray: camera -> pano frame
    lon = np.arctan2(rays[..., 0], rays[..., 2])
    lat = np.arctan2(-rays[..., 1], np.hypot(rays[..., 0], rays[..., 2]))
    u = (lon / (2 * np.pi) + 0.5) * pano_w - 0.5
    v = (0.5 - lat / np.pi) * pano_h - 0.5
    u = np.mod(u, pano_w).astype(np.float32)  # BORDER_WRAP below handles the seam column
    v = np.clip(v, 0, pano_h - 1).astype(np.float32)
    m1, m2 = cv2.convertMaps(u, v, cv2.CV_16SC2)  # fixed-point maps: ~2x faster remap
    return m1, m2, K


@lru_cache(maxsize=64)
def _maps_unlevelled(pano_w, pano_h, yaw_deg, pitch_deg, fov_deg, out_w, out_h):
    return _maps(pano_w, pano_h, view_rotation(yaw_deg, pitch_deg), fov_deg, out_w, out_h)


def perspective(equirect_img, yaw_deg, pitch_deg=0.0, fov_deg=90.0, out_w=640, out_h=480, level=None):
    """Render a pinhole view from an equirectangular panorama.

    equirect_img: HxWxC numpy array (any channel order, returned unchanged) or a PIL image.
    yaw_deg:   turn right from the pano's centre column (Mapillary: the compass_angle direction).
    pitch_deg: look up (> 0) or down (< 0).
    fov_deg:   horizontal field of view; vertical fov follows from out_h / out_w.
    level:     optional R_level_from_pano from level_rotation(meta): yaw/pitch are then measured
               from the gravity-levelled frame, so pitch 0 gives a level horizon.
    Returns (image HxWxC uint8 numpy array, K 3x3, R 3x3) where R = R_cam_from_pano, i.e.
    X_cam = R @ X_pano (see the module docstring for the frame definitions).
    """
    img = np.asarray(equirect_img)
    if level is None:
        R = view_rotation(yaw_deg, pitch_deg)
        m1, m2, K = _maps_unlevelled(img.shape[1], img.shape[0], float(yaw_deg), float(pitch_deg),
                                     float(fov_deg), int(out_w), int(out_h))
    else:
        R = view_rotation(yaw_deg, pitch_deg) @ np.asarray(level, dtype=np.float64)
        m1, m2, K = _maps(img.shape[1], img.shape[0], R, float(fov_deg), int(out_w), int(out_h))
    out = cv2.remap(img, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    return out, K.copy(), R


def pano_world_rotation(pano_meta):
    """R_pano_from_world (X_P = R @ X_W, world = east/north/up) from Mapillary computed_rotation,
    or None when the metadata does not have it."""
    r = pano_meta.get("computed_rotation")
    if not r:
        return None
    return cv2.Rodrigues(np.asarray(r, dtype=np.float64))[0]


def level_rotation(pano_meta):
    """R_level_from_pano for a Mapillary pano (None without computed_rotation).  The levelled
    frame L keeps the heading of the pano's centre column but has y_L = world down, so
    `perspective(.., level=level_rotation(meta))` views have a level horizon."""
    R_pw = pano_world_rotation(pano_meta)
    if R_pw is None:
        return None
    z = R_pw[2]  # pano z axis in world (east, north, up)
    if math.hypot(z[0], z[1]) < 1e-3:
        return None
    h = math.atan2(z[0], z[1])
    z_l = np.array([math.sin(h), math.cos(h), 0.0])
    y_l = np.array([0.0, 0.0, -1.0])
    R_lw = np.stack([np.cross(y_l, z_l), y_l, z_l])  # rows: level axes in world
    return R_lw @ R_pw.T


def heading_of(R_cam_from_world):
    """Compass heading (deg, 0 = north, 90 = east) of a camera's optical axis."""
    z = R_cam_from_world[2]
    return math.degrees(math.atan2(z[0], z[1])) % 360


def absolute_heading(pano_meta, yaw_deg, pitch_deg=0.0, leveled=True):
    """Compass heading (0 = north, 90 = east) of the virtual view
    `perspective(.., yaw_deg, pitch_deg, .., level=level_rotation(meta) if leveled else None)`.

    With computed_rotation the full SfM orientation is used, so it is exact for levelled and
    unlevelled views alike (levelled: computed_compass_angle + yaw).  Without it, falls back to
    (computed_)compass_angle + yaw."""
    R_pw = pano_world_rotation(pano_meta)
    if R_pw is not None:
        level = level_rotation(pano_meta) if leveled else None
        R = view_rotation(yaw_deg, pitch_deg) @ (level if level is not None else np.eye(3))
        return heading_of(R @ R_pw)
    base = next((pano_meta[k] for k in ("computed_compass_angle", "heading", "compass_angle")
                 if pano_meta.get(k) is not None), 0.0)
    return (base + yaw_deg) % 360


# ----------------------------------------------------------------------------------------------
# self-tests
# ----------------------------------------------------------------------------------------------

def _label(img_rgb, text):
    out = img_rgb.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(out, text, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def _load_index(root):
    idx = json.loads((root / "index.json").read_text())
    return [r for r in idx if (root / r["area"] / f"{r['id']}.jpg").exists()]


def horizon_curve(level, pano_w, pano_h, n=720):
    """Equirect pixel coordinates of the true (gravity) horizon, for drawing."""
    a = np.linspace(-np.pi, np.pi, n)
    rays = np.stack([np.sin(a), np.zeros_like(a), np.cos(a)], -1) @ level  # level -> pano frame
    lon = np.arctan2(rays[:, 0], rays[:, 2])
    lat = np.arctan2(-rays[:, 1], np.hypot(rays[:, 0], rays[:, 2]))
    pts = np.stack([(lon / (2 * np.pi) + 0.5) * pano_w, (0.5 - lat / np.pi) * pano_h], -1)
    return pts[np.argsort(pts[:, 0])]


def contact_sheet(root, pano_id=None, out_path=None):
    """8 levelled views (FOV 90, yaw every 45 deg, the views match.py indexes), 4 unlevelled
    pitch-0 views for comparison, and the equirect with the SfM horizon and view centres."""
    refs = _load_index(root)
    panos = [r for r in refs if r["is_pano"]]
    if pano_id:
        meta = next(r for r in panos if r["id"] == pano_id)
    else:  # most tilted of the 50 newest panos: the hardest case for levelling
        recent = sorted(panos, key=lambda r: -r["captured_at"])[:50]
        meta = max(recent, key=lambda r: abs(level_rotation(r)[1, 1] - 1) if level_rotation(r) is not None else -1)
    eq = cv2.cvtColor(cv2.imread(str(root / meta["area"] / f"{meta['id']}.jpg")), cv2.COLOR_BGR2RGB)
    level = level_rotation(meta)
    tiles = []
    for yaw in range(0, 360, 45):
        view = perspective(eq, yaw, 0, 90, 512, 384, level=level)[0]
        tiles.append(_label(view, f"levelled yaw {yaw:3d}  heading {absolute_heading(meta, yaw):5.1f}"))
    raw = [_label(perspective(eq, yaw, 0, 90, 512, 384)[0], f"NOT levelled yaw {yaw:3d}")
           for yaw in range(0, 360, 90)]
    sheet = np.vstack([np.hstack(tiles[:4]), np.hstack(tiles[4:]), np.hstack(raw)])
    eq_small = cv2.resize(eq, (sheet.shape[1], sheet.shape[1] // 2), interpolation=cv2.INTER_AREA)
    if level is not None:
        pts = horizon_curve(level, eq_small.shape[1], eq_small.shape[0])
        cv2.polylines(eq_small, [pts.astype(np.int32).reshape(-1, 1, 2)], False, (255, 0, 255), 3)
    for yaw in range(0, 360, 45):  # where each view centre sits (levelled frame keeps the heading)
        x = int(((yaw + 180) % 360) / 360 * eq_small.shape[1])
        cv2.line(eq_small, (x, 0), (x, eq_small.shape[0]), (255, 255, 0), 2)
        cv2.putText(eq_small, str(yaw), (x + 4, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
    tilt = math.degrees(math.acos(min(1.0, level[1, 1]))) if level is not None else float("nan")
    eq_small = _label(eq_small, f"pano {meta['id']} ({meta['area']}) {eq.shape[1]}x{eq.shape[0]}; centre column = "
                                f"computed_compass_angle {meta.get('heading', 0):.1f}; magenta = SfM horizon "
                                f"(frame tilt {tilt:.1f} deg)")
    out_path = out_path or HERE / "results" / "pano_views_check.jpg"
    cv2.imwrite(str(out_path), cv2.cvtColor(np.vstack([sheet, eq_small]), cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"wrote {out_path} from pano {meta['id']} ({eq.shape[1]}x{eq.shape[0]}, tilt {tilt:.1f} deg)")
    return meta


def _dist_m(a, b):
    dy = (a["lat"] - b["lat"]) * 111320
    dx = (a["lon"] - b["lon"]) * 111320 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy)


def verify_heading(root, n_pairs=30, max_dist=8.0, out_stem="pano_heading_check"):
    """Empirical check of the heading convention.

    For pano / perspective-photo pairs taken within max_dist metres of each other (different
    sequences, perspective camera model), render levelled pano views every 10 degrees and find the
    view with the most ALIKED+LightGlue+MAGSAC inliers against the photo (coarse).  Then, on that
    view, estimate the calibrated relative rotation photo<-view from the essential matrix (photo
    focal from Mapillary camera_parameters) and predict the photo's compass heading as
    heading_of(R_rel @ R_view_from_world).  If the convention is right the prediction matches the
    photo's own computed_compass_angle to within a few degrees."""
    import torch
    from lightglue import ALIKED, LightGlue
    from lightglue.utils import rbd
    from mapillary_harvest import load_env, lookup

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cuda":
        torch.cuda.set_per_process_memory_fraction(0.35)
    extractor = ALIKED(max_num_keypoints=2048).eval().to(dev)
    matcher = LightGlue(features="aliked").eval().to(dev)

    refs = list({r["id"]: r for r in _load_index(root)}.values())
    panos = [r for r in refs if r["is_pano"] and r.get("computed_rotation")]
    persp = [r for r in refs if not r["is_pano"] and r.get("camera_type") == "perspective"
             and r.get("computed_rotation")]
    pairs = []
    for p in panos:
        near = [(_dist_m(p, q), q) for q in persp if abs(q["lat"] - p["lat"]) < 1e-4
                and p.get("sequence") != q.get("sequence")]
        near = [t for t in near if t[0] < max_dist]
        if near:
            d, q = min(near, key=lambda t: t[0])
            pairs.append((p, q, d))
    rng = np.random.default_rng(0)
    rng.shuffle(pairs)
    seen, chosen = set(), []
    for p, q, d in pairs:  # one pair per area so the check is not one street repeated
        if p["area"] not in seen:
            seen.add(p["area"])
            chosen.append((p, q, d))
    chosen = chosen[:n_pairs]
    load_env(HERE / ".env")
    cam = lookup([q["id"] for _, q, _ in chosen], fields="id,camera_parameters,width,height")

    def feats(rgb):
        t = torch.from_numpy(rgb.astype(np.float32) / 255).permute(2, 0, 1).to(dev)
        return extractor.extract(t)

    def match(f0, f1):
        m = rbd(matcher({"image0": f0, "image1": f1}))["matches"].cpu().numpy()
        if len(m) < 8:
            return 0, None, None
        k0 = rbd(f0)["keypoints"].cpu().numpy()[m[:, 0]]
        k1 = rbd(f1)["keypoints"].cpu().numpy()[m[:, 1]]
        _, mask = cv2.findFundamentalMat(k0, k1, cv2.USAC_MAGSAC, 2.0, 0.999, 5000)
        if mask is None:
            return 0, None, None
        keep = mask.ravel().astype(bool)
        return int(keep.sum()), k0[keep], k1[keep]

    rows, sheet = [], []
    with torch.inference_mode():
        for p, q, d in chosen:
            eq = cv2.cvtColor(cv2.imread(str(root / p["area"] / f"{p['id']}.jpg")), cv2.COLOR_BGR2RGB)
            ph = cv2.cvtColor(cv2.imread(str(root / q["area"] / f"{q['id']}.jpg")), cv2.COLOR_BGR2RGB)
            ph = cv2.resize(ph, (640, round(640 * ph.shape[0] / ph.shape[1])), interpolation=cv2.INTER_AREA)
            fq = feats(ph)
            level = level_rotation(p)
            scores = []
            for yaw in range(0, 360, 10):
                scores.append(match(fq, feats(perspective(eq, yaw, 0, 90, 640, 480, level=level)[0]))[0])
            best = int(np.argmax(scores))
            yaw = best * 10
            coarse = absolute_heading(p, yaw)
            row = {"pano": p["id"], "photo": q["id"], "area": p["area"], "dist_m": round(d, 1),
                   "best_yaw": yaw, "best_inliers": scores[best], "photo_heading": round(q["heading"], 1),
                   "coarse_view_heading": round(coarse, 1),
                   "coarse_diff_deg": round((q["heading"] - coarse + 180) % 360 - 180, 1)}
            # precise: calibrated relative rotation from the essential matrix
            cp = (cam.get(q["id"]) or {}).get("camera_parameters")
            view, K_v, R_vp = perspective(eq, yaw, 0, 90, 640, 480, level=level)
            n_in, k_photo, k_view = match(fq, feats(view))
            if cp and n_in >= 30:
                f_ph = cp[0] * max(ph.shape[:2])
                c_ph = np.array([(ph.shape[1] - 1) / 2, (ph.shape[0] - 1) / 2])
                x_view = (k_view - K_v[:2, 2]) / K_v[0, 0]
                x_photo = (k_photo - c_ph) / f_ph
                E, emask = cv2.findEssentialMat(x_view, x_photo, np.eye(3), cv2.RANSAC, 0.999, 1.5 / f_ph)
                if E is not None and E.shape == (3, 3):
                    n_e, R_rel, _, _ = cv2.recoverPose(E, x_view, x_photo, np.eye(3), mask=emask)
                    R_view_world = R_vp @ pano_world_rotation(p)
                    pred = heading_of(R_rel @ R_view_world)
                    row.update({"essential_inliers": int(n_e), "photo_focal_norm": cp[0],
                                "predicted_photo_heading": round(pred, 1),
                                "diff_deg": round((q["heading"] - pred + 180) % 360 - 180, 1)})
            rows.append(row)
            print(f"  {p['area']} pano {p['id']} vs photo {q['id']} ({d:.1f} m): best yaw {yaw:3d} "
                  f"({scores[best]} inl), coarse diff {row['coarse_diff_deg']:+6.1f}; "
                  f"essential: {row.get('essential_inliers')} inl, diff {row.get('diff_deg')}")
            if len(sheet) < 6 and scores[best] >= 60:  # visual: photo | levelled view AT the photo heading
                yaw_for_photo = (q["heading"] - absolute_heading(p, 0)) % 360
                v = perspective(eq, yaw_for_photo, 0, 90, 640, 480, level=level)[0]
                sheet.append(np.hstack([
                    _label(cv2.resize(ph, (640, 480)), f"photo {q['id']} heading {q['heading']:.0f}"),
                    _label(v, f"pano view at heading {q['heading']:.0f} (yaw {yaw_for_photo:.0f}), {d:.1f} m away")]))
    good = [r for r in rows if r.get("essential_inliers", 0) >= 40]
    diffs = np.array([r["diff_deg"] for r in good])
    summary = {"method": "levelled pano views every 10 deg; best view by inliers; essential-matrix relative "
                         "rotation to the photo; predicted vs Mapillary computed_compass_angle of the photo",
               "pairs": len(rows), "confident_pairs": len(good),
               "median_diff_deg": round(float(np.median(diffs)), 1) if len(diffs) else None,
               "median_abs_diff_deg": round(float(np.median(np.abs(diffs))), 1) if len(diffs) else None,
               "within_5deg": int((np.abs(diffs) <= 5).sum()), "within_10deg": int((np.abs(diffs) <= 10).sum()),
               "rows": rows}
    print(f"heading check: {len(good)} confident pairs; median diff {summary['median_diff_deg']} deg, median "
          f"|diff| {summary['median_abs_diff_deg']} deg; {summary['within_5deg']} within 5 deg, "
          f"{summary['within_10deg']} within 10 deg")
    (HERE / "results" / f"{out_stem}.json").write_text(json.dumps(summary, indent=2))
    if sheet:
        cv2.imwrite(str(HERE / "results" / f"{out_stem}.jpg"),
                    cv2.cvtColor(np.vstack(sheet), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return summary


def _self_check_math():
    # centre column / horizon must map to the camera axis, yaw must turn right, pitch up
    eq = np.zeros((64, 128, 3), np.uint8)
    eq[:, 64:65] = 255  # just right of centre (lon ~ +1.4 deg)
    v = perspective(eq, 0, 0, 90, 101, 75)[0]
    assert v[37, 50:53].max() > 100 and v[37, :45].max() == 0, "centre column should land in the centre"
    eq2 = np.zeros((64, 128, 3), np.uint8)
    eq2[:, 96] = 255  # lon ~ +90 deg (to the right)
    assert perspective(eq2, 90, 0, 60, 101, 75)[0][37, 48:55].max() > 100, "yaw +90 should look right"
    eq3 = np.zeros((64, 128, 3), np.uint8)
    eq3[16] = 255  # lat ~ +45 deg (up)
    assert perspective(eq3, 0, 45, 60, 101, 75)[0][35:42, 50].max() > 100, "pitch +45 should look up"
    R = view_rotation(30, 10)
    assert np.allclose(R @ R.T, np.eye(3)) and abs(np.linalg.det(R) - 1) < 1e-9
    # a pano whose z axis points east (heading 90): yaw 90 must then face south (180)
    # rows of R_pano_from_world are the pano axes in world coords: x = south, y = down, z = east
    r_east = cv2.Rodrigues(np.array([[0, -1, 0], [0, 0, -1], [1, 0, 0]], float))[0].ravel().tolist()
    assert abs(absolute_heading({"computed_rotation": r_east}, 0) - 90) < 1e-6
    assert abs(absolute_heading({"computed_rotation": r_east}, 90) - 180) < 1e-6
    assert abs(absolute_heading({"heading": 350.0}, 20) - 10) < 1e-9


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(HERE / "data" / "mly"))
    ap.add_argument("--pano", help="pano id for the contact sheet (default: a recent 2048-px one)")
    ap.add_argument("--verify-heading", action="store_true", help="empirical heading check (GPU)")
    args = ap.parse_args()
    _self_check_math()
    print("projection math checks passed")
    contact_sheet(Path(args.root), args.pano)
    if args.verify_heading:
        verify_heading(Path(args.root))
