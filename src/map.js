// Dependency-free Web Mercator map with animated camera movement.
const tileSize = 256;
const clampZoom = z => Math.max(10, Math.min(18, z));
function project([lng, lat], z) {
  const size = tileSize * 2 ** z;
  const sin = Math.sin(Math.max(-85, Math.min(85, lat)) * Math.PI / 180);
  return [(lng + 180) / 360 * size, (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * size];
}
function unproject([x, y], z) {
  const size = tileSize * 2 ** z;
  return [x / size * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y / size))) * 180 / Math.PI];
}
export class CivicMap {
  constructor(element, { onSelect, onEmpty, onMove, onArea, icon, colorFor = () => '#4ea8ff', assets = [], boundaries = [], home = [-79.397, 43.661] }) {
    Object.assign(this, { element, onSelect, onEmpty, onMove, onArea, icon, colorFor, assets, home, center: home, zoom: 13, issues: [], selected: [], layers: [], activeArea: '', mode: 'pan', drag: null, pinch: null, pointers: new Map(), showHeat: false, tileCache: new Map(), motionFrame: null, renderFrame: null, lastWheel: 0, backdropTimer: null });
    // Ward outlines ({ id, name, rings }), labelled at the centroid of each ward's largest ring.
    this.boundaries = boundaries.map(b => {
      const area = ring => ring.reduce((sum, [x, y], i) => { const [x2, y2] = ring[(i + 1) % ring.length]; return sum + x * y2 - x2 * y; }, 0) / 2;
      const ring = b.rings.reduce((best, r) => Math.abs(area(r)) > Math.abs(area(best)) ? r : best), a = area(ring);
      const c = ring.reduce(([cx, cy], [x, y], i) => { const [x2, y2] = ring[(i + 1) % ring.length], f = x * y2 - x2 * y; return [cx + (x + x2) * f, cy + (y + y2) * f]; }, [0, 0]);
      return { ...b, labelAt: [c[0] / (6 * a), c[1] / (6 * a)] };
    });
    element.innerHTML = '<div class="map-fallback" aria-hidden="true"><div class="fallback-grid"></div><span>TORONTO</span><i>Lake Ontario</i></div><div class="map-scene"><div class="tile-layer"></div><div class="infrastructure-layer"></div><div class="marker-layer"></div></div><div class="box-drawing"></div><div class="tile-warning" hidden>Map tiles unavailable · schematic background</div>';
    this.bindScene(element.querySelector('.map-scene'));
    this.box = element.querySelector('.box-drawing');
    this.tooltip = document.createElement('div');
    this.tooltip.className = 'map-hover-preview';
    this.tooltip.id = 'map-hover-preview';
    this.tooltip.setAttribute('role', 'tooltip');
    this.tooltip.hidden = true;
    element.append(this.tooltip);
    element.tabIndex = 0;
    element.setAttribute('aria-description', 'Arrow keys pan. Plus and minus zoom. Home returns to Toronto.');
    this.handlers = {
      pointerdown: e => this.pointerDown(e),
      pointermove: e => this.pointerMove(e),
      pointerup: e => this.pointerUp(e),
      pointercancel: e => { this.pointers.delete(e.pointerId); this.drag = null; this.pinch = null; this.box.style.display = 'none'; this.element.classList.remove('is-dragging'); },
      // Text in the map (the offline fallback labels) must never start a native text drag: it cancels panning.
      dragstart: e => e.preventDefault(),
      wheel: e => {
        e.preventDefault();
        // Trackpads emit many small wheel events; one camera step per gesture slice.
        if (performance.now() - this.lastWheel < 140 || Math.abs(e.deltaY) < 2) return;
        this.lastWheel = performance.now();
        const r = element.getBoundingClientRect();
        this.setZoom(Math.round(this.targetZoom ?? this.zoom) + (e.deltaY < 0 ? 1 : -1), [e.clientX - r.left, e.clientY - r.top]);
      },
      dblclick: e => {
        if (e.target.closest('button')) return;
        const r = element.getBoundingClientRect();
        this.setZoom(Math.round(this.zoom) + 1, [e.clientX - r.left, e.clientY - r.top]);
      },
      keydown: e => {
        if (e.target !== element) return;
        const delta = { ArrowLeft: [-100, 0], ArrowRight: [100, 0], ArrowUp: [0, -100], ArrowDown: [0, 100] }[e.key];
        if (delta) {
          e.preventDefault();
          const c = project(this.center, this.zoom);
          this.animateTo(unproject([c[0] + delta[0], c[1] + delta[1]], this.zoom), this.zoom, 250);
        } else if (['+', '=', '-'].includes(e.key)) { e.preventDefault(); this.setZoom(Math.round(this.zoom) + (e.key === '-' ? -1 : 1)); }
        else if (e.key === 'Home') { e.preventDefault(); this.flyTo(this.home, 13); }
      },
    };
    for (const [event, handler] of Object.entries(this.handlers)) element.addEventListener(event, handler, event === 'wheel' ? { passive: false } : undefined);
    this.observer = new ResizeObserver(() => { this.stopMotion(); this.render(); });
    this.observer.observe(element);
  }
  bindScene(scene) {
    this.scene = scene;
    this.tiles = scene.querySelector('.tile-layer');
    this.markers = scene.querySelector('.marker-layer');
  }
  destroy() {
    this.stopMotion(); cancelAnimationFrame(this.renderFrame); clearTimeout(this.backdropTimer);
    this.observer.disconnect();
    for (const [event, handler] of Object.entries(this.handlers)) this.element.removeEventListener(event, handler);
  }
  stopMotion() {
    if (this.motionFrame !== null) { cancelAnimationFrame(this.motionFrame); this.motionFrame = null; }
    this.targetZoom = null;
    this.element.classList.remove('is-moving');
    if (this.tooltip) this.tooltip.hidden = true;
  }
  setData(issues, selected = []) { this.stopMotion(); this.issues = issues; this.selected = selected; this.render(); }
  setZoom(z, anchor = [this.element.clientWidth / 2, this.element.clientHeight / 2]) {
    z = clampZoom(Math.round(z));
    const c = project(this.center, this.zoom);
    const offset = [anchor[0] - this.element.clientWidth / 2, anchor[1] - this.element.clientHeight / 2];
    const fixedPoint = unproject([c[0] + offset[0], c[1] + offset[1]], this.zoom);
    const p = project(fixedPoint, z);
    this.animateTo(unproject([p[0] - offset[0], p[1] - offset[1]], z), z, 360);
  }
  flyTo(coords, z = 14) { this.animateTo(coords, clampZoom(z), 600); }
  fitTo(coords, { top = 155, right = 55, bottom = 115, left = 55 } = {}, maxZoom = 15) {
    if (!coords.length) return;
    const points = coords.map(c => project(c, 0));
    const minX = Math.min(...points.map(p => p[0])), maxX = Math.max(...points.map(p => p[0]));
    const minY = Math.min(...points.map(p => p[1])), maxY = Math.max(...points.map(p => p[1]));
    const width = Math.max(64, this.element.clientWidth - left - right);
    const height = Math.max(64, this.element.clientHeight - top - bottom);
    const z = Math.min(maxZoom, clampZoom(Math.floor(Math.log2(Math.min(width / Math.max(0.00001, maxX - minX), height / Math.max(0.00001, maxY - minY))))));
    const center = unproject([((minX + maxX) / 2) * 2 ** z - (left - right) / 2, ((minY + maxY) / 2) * 2 ** z - (top - bottom) / 2], z);
    this.animateTo(center, z, 600);
  }
  animateTo(coords, z, duration) {
    this.stopMotion();
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { this.center = coords; this.zoom = z; this.render(); this.onMove?.(); return; }
    // Rebase an interrupted camera at its current visual position.
    this.render();
    const startZoom = this.zoom, start = project(this.center, startZoom), end = project(coords, startZoom);
    if (Math.abs(z - startZoom) < 0.001 && Math.hypot(end[0] - start[0], end[1] - start[1]) < 0.5) return;
    this.targetZoom = z;
    const scene = this.scene, startTime = performance.now();
    this.element.classList.add('is-moving');
    const step = now => {
      const t = Math.min(1, (now - startTime) / duration), eased = 1 - (1 - t) ** 3;
      this.zoom = startZoom + (z - startZoom) * eased;
      const camera = [start[0] + (end[0] - start[0]) * eased, start[1] + (end[1] - start[1]) * eased];
      this.center = unproject(camera, startZoom);
      const scale = 2 ** (this.zoom - startZoom);
      scene.style.transform = `translate(${(start[0] - camera[0]) * scale}px, ${(start[1] - camera[1]) * scale}px) scale(${scale})`;
      scene.style.setProperty('--camera-scale', scale);
      if (t < 1) this.motionFrame = requestAnimationFrame(step);
      else {
        this.motionFrame = null; this.targetZoom = null;
        this.center = coords; this.zoom = z;
        this.finishMotion(); this.onMove?.();
      }
    };
    this.motionFrame = requestAnimationFrame(step);
  }
  finishMotion() {
    // Keep transformed old tiles underneath until destination tiles have loaded.
    this.element.querySelector('.map-transition-backdrop')?.remove();
    const old = this.scene;
    old.classList.add('map-transition-backdrop');
    old.querySelector('.marker-layer').replaceChildren();
    old.querySelector('.infrastructure-layer').replaceChildren();
    const scene = document.createElement('div'); scene.className = 'map-scene';
    scene.innerHTML = '<div class="tile-layer"></div><div class="infrastructure-layer"></div><div class="marker-layer"></div>';
    old.after(scene); this.bindScene(scene); this.render();
    const reveal = () => {
      old.classList.add('retiring');
      this.backdropTimer = setTimeout(() => old.remove(), 180);
    };
    const pending = [...this.tiles.children].filter(img => !img.complete);
    this.backdropTimer = setTimeout(reveal, 1500);
    if (!pending.length) { clearTimeout(this.backdropTimer); reveal(); }
    else Promise.all(pending.map(img => new Promise(resolve => {
      img.addEventListener('load', resolve, { once: true });
      img.addEventListener('error', resolve, { once: true });
    }))).then(() => { if (!old.isConnected) return; clearTimeout(this.backdropTimer); reveal(); });
    this.element.classList.remove('is-moving');
  }
  position(coords) {
    const p = project(coords, this.zoom), c = project(this.center, this.zoom);
    return [p[0] - c[0] + this.element.clientWidth / 2, p[1] - c[1] + this.element.clientHeight / 2];
  }
  coordsAt([x, y]) {
    const c = project(this.center, this.zoom);
    return unproject([c[0] + x - this.element.clientWidth / 2, c[1] + y - this.element.clientHeight / 2], this.zoom);
  }
  /** Pans just enough to bring a point into the area not covered by panels, centring it there. */
  ensureVisible(coords, { top = 0, right = 0, bottom = 0, left = 0 } = {}) {
    const [x, y] = this.position(coords), w = this.element.clientWidth, h = this.element.clientHeight;
    if (x >= left && x <= w - right && y >= top && y <= h - bottom) return;
    const c = project(this.center, this.zoom);
    const target = [left + Math.max(0, w - left - right) / 2, top + Math.max(0, h - top - bottom) / 2];
    this.animateTo(unproject([c[0] + x - target[0], c[1] + y - target[1]], this.zoom), this.zoom, 420);
  }
  pointerDown(e) {
    if (e.target.closest('button') || e.button !== 0) return;
    this.element.setPointerCapture(e.pointerId);
    this.pointers.set(e.pointerId, [e.clientX, e.clientY]);
    if (this.pointers.size === 2) { this.startPinch(); return; }
    if (this.pointers.size > 2) return;
    this.stopMotion(); this.render();
    this.drag = { x: e.clientX, y: e.clientY, lastX: e.clientX, lastY: e.clientY, lastTime: performance.now(), vx: 0, vy: 0, center: project(this.center, this.zoom), moved: false };
    this.element.classList.add('is-dragging');
  }
  pinchGeometry() {
    const [a, b] = [...this.pointers.values()], r = this.element.getBoundingClientRect();
    return { distance: Math.max(1, Math.hypot(a[0] - b[0], a[1] - b[1])), mid: [(a[0] + b[0]) / 2 - r.left, (a[1] + b[1]) / 2 - r.top] };
  }
  startPinch() {
    // A second finger turns the gesture into a pinch-zoom anchored between both fingers.
    this.drag = null; this.box.style.display = 'none';
    this.stopMotion(); this.render();
    const { distance, mid } = this.pinchGeometry();
    this.pinch = { distance, zoom: this.zoom, anchor: this.coordsAt(mid) };
    this.element.classList.add('is-dragging');
  }
  pointerMove(e) {
    if (this.pointers.has(e.pointerId)) this.pointers.set(e.pointerId, [e.clientX, e.clientY]);
    if (this.pinch) {
      if (this.pointers.size < 2) return;
      const { distance, mid } = this.pinchGeometry();
      const z = clampZoom(this.pinch.zoom + Math.log2(distance / this.pinch.distance)), p = project(this.pinch.anchor, z);
      this.zoom = z;
      this.center = unproject([p[0] - (mid[0] - this.element.clientWidth / 2), p[1] - (mid[1] - this.element.clientHeight / 2)], z);
      if (!this.renderFrame) this.renderFrame = requestAnimationFrame(() => { this.renderFrame = null; this.render(); });
      return;
    }
    if (!this.drag) return;
    const d = this.drag, dx = e.clientX - d.x, dy = e.clientY - d.y, now = performance.now(), dt = Math.max(1, now - d.lastTime);
    d.moved ||= Math.abs(dx) + Math.abs(dy) > 5;
    d.vx = (e.clientX - d.lastX) / dt; d.vy = (e.clientY - d.lastY) / dt;
    d.lastX = e.clientX; d.lastY = e.clientY; d.lastTime = now;
    if (this.mode === 'box') {
      const r = this.element.getBoundingClientRect();
      Object.assign(this.box.style, { display: 'block', left: Math.min(e.clientX, d.x) - r.left + 'px', top: Math.min(e.clientY, d.y) - r.top + 'px', width: Math.abs(dx) + 'px', height: Math.abs(dy) + 'px' });
    } else {
      this.center = unproject([d.center[0] - dx, d.center[1] - dy], this.zoom);
      if (!this.renderFrame) this.renderFrame = requestAnimationFrame(() => { this.renderFrame = null; this.render(); });
    }
  }
  pointerUp(e) {
    this.pointers.delete(e.pointerId);
    if (this.pinch) {
      if (this.pointers.size) return; // wait for the last finger
      this.pinch = null; this.element.classList.remove('is-dragging');
      cancelAnimationFrame(this.renderFrame); this.renderFrame = null;
      // Settle on a whole zoom level so tiles stay crisp.
      const r = this.element.getBoundingClientRect(), whole = Math.round(this.zoom);
      if (Math.abs(this.zoom - whole) < 0.01) { this.zoom = whole; this.render(); this.onMove?.(); }
      else this.setZoom(whole, [e.clientX - r.left, e.clientY - r.top]);
      return;
    }
    if (!this.drag) return;
    const d = this.drag; this.drag = null; this.box.style.display = 'none';
    this.element.classList.remove('is-dragging');
    cancelAnimationFrame(this.renderFrame); this.renderFrame = null;
    if (this.mode === 'box' && d.moved) {
      const r = this.element.getBoundingClientRect(), x1 = Math.min(d.x, e.clientX) - r.left, x2 = Math.max(d.x, e.clientX) - r.left, y1 = Math.min(d.y, e.clientY) - r.top, y2 = Math.max(d.y, e.clientY) - r.top;
      const ids = this.issues.filter(i => { const [x, y] = this.position(i.geometry.coordinates); return x >= x1 && x <= x2 && y >= y1 && y <= y2; }).map(i => i.issue_id);
      this.onSelect(ids, 'multi', e);
    } else if (!d.moved) this.showHeat ? this.pickHeat(e) : this.onEmpty();
    else if (this.mode === 'pan' && performance.now() - d.lastTime < 80 && Math.hypot(d.vx, d.vy) > 0.12) {
      const c = project(this.center, this.zoom), limit = v => Math.max(-170, Math.min(170, v * 140));
      this.animateTo(unproject([c[0] - limit(d.vx), c[1] - limit(d.vy)], this.zoom), this.zoom, 340);
    } else { this.render(); this.onMove?.(); }
  }
  render() {
    const width = this.element.clientWidth, height = this.element.clientHeight;
    if (!width || !height) return;
    this.scene.style.transform = ''; this.scene.style.setProperty('--camera-scale', 1);
    if (this.tooltip) this.tooltip.hidden = true;
    const z = Math.round(this.zoom), scale = 2 ** (this.zoom - z), c = project(this.center, z);
    const left = c[0] - width / 2 / scale, top = c[1] - height / 2 / scale;
    const fragment = document.createDocumentFragment();
    // One tile of overscan gives the camera room to animate without empty edges.
    for (let x = Math.floor(left / 256) - 1; x <= Math.floor((left + width / scale) / 256) + 1; x++) {
      for (let y = Math.floor(top / 256) - 1; y <= Math.floor((top + height / scale) / 256) + 1; y++) {
        if (y < 0 || y >= 2 ** z) continue;
        const key = `${z}/${((x % 2 ** z) + 2 ** z) % 2 ** z}/${y}`;
        let img = this.tileCache.get(key);
        if (!img || (img.parentElement && img.parentElement !== this.tiles)) {
          img = document.createElement('img'); img.alt = ''; img.draggable = false;
          img.src = `https://tile.openstreetmap.org/${key}.png`;
          img.onerror = () => { this.element.querySelector('.tile-warning').hidden = false; img.style.opacity = 0; };
          this.tileCache.set(key, img);
        }
        Object.assign(img.style, { left: (x * 256 - left) * scale + 'px', top: (y * 256 - top) * scale + 'px', width: 256 * scale + 0.5 + 'px', height: 256 * scale + 0.5 + 'px' });
        fragment.append(img);
      }
    }
    this.tiles.replaceChildren(fragment);
    if (this.tileCache.size > 160) for (const [key, img] of this.tileCache) { if (!img.isConnected) this.tileCache.delete(key); if (this.tileCache.size <= 120) break; }
    let visible = this.issues.map(i => ({ issue: i, p: this.position(i.geometry.coordinates) })).filter(({ p }) => p[0] > -25 && p[0] < width + 25 && p[1] > -25 && p[1] < height + 25);
    // Density mode replaces pins with a heat surface; selected issues keep their pins so an open panel still points somewhere.
    const heat = this.showHeat ? this.renderHeat(width, height) : null;
    if (heat) visible = visible.filter(({ issue }) => this.selected.includes(issue.issue_id));
    const groups = [];
    for (const point of visible) {
      const group = groups.find(g => Math.hypot(g.p[0] - point.p[0], g.p[1] - point.p[1]) < (this.zoom < 14 ? 48 : 25));
      if (group) group.items.push(point.issue); else groups.push({ p: point.p, items: [point.issue] });
    }
    const oldMarkers = new Map([...this.markers.children].map(b => [b.dataset.key, b]));
    const markerFragment = document.createDocumentFragment();
    if (heat) markerFragment.append(heat);
    // A selected issue gets an uncertainty area rather than implying an exact location.
    if (this.selected.length === 1) {
      const issue = this.issues.find(i => i.issue_id === this.selected[0]);
      if (issue) {
        const [x, y] = this.position(issue.geometry.coordinates);
        const radius = Math.max(2, issue.location_radius_m / (156543.03392 * Math.cos(issue.geometry.coordinates[1] * Math.PI / 180) / 2 ** this.zoom));
        const area = document.createElement('div'); area.className = 'uncertainty-area';
        area.style.cssText = `left:${x}px;top:${y}px;width:${radius * 2}px;height:${radius * 2}px`;
        area.setAttribute('aria-label', `Approximate location within ${issue.location_radius_m} metres`);
        markerFragment.append(area);
      }
    }
    for (const group of groups) {
      const first = group.items[0], multi = group.items.length > 1, key = group.items.map(i => i.issue_id).join(',');
      // High severity gets a "!" badge, so severity never depends on colour alone.
      const high = group.items.filter(i => i.severity === 'High').length;
      const button = oldMarkers.get(key) || document.createElement('button');
      button.dataset.key = key;
      button.className = `map-pin ${multi ? 'cluster' : ''} ${high ? 'sev-high' : ''} ${group.items.some(i => this.selected.includes(i.issue_id)) ? 'selected' : ''}`;
      button.style.cssText = `left:${group.p[0]}px;top:${group.p[1]}px;--pin:${this.colorFor(first.issue_type)}`;
      button.innerHTML = multi ? `<span>${group.items.length}</span>` : this.icon(first.issue_type);
      const label = multi ? `${group.items.length} issues${high ? `, ${high} high severity` : ''} · click to explore` : `${first.issue_type} · ${first.severity} severity · ${first.address}`;
      button.removeAttribute('title');
      button.setAttribute('aria-label', label);
      button.onpointerenter = e => { if (e.pointerType === 'mouse' && !this.drag) this.preview(group, button); };
      button.onpointerleave = button.onblur = () => { this.tooltip.hidden = true; button.removeAttribute('aria-describedby'); };
      button.onfocus = () => this.preview(group, button);
      button.onclick = e => { e.stopPropagation(); this.tooltip.hidden = true; this.onSelect(group.items.map(i => i.issue_id), multi ? 'cluster' : 'issue', e); };
      markerFragment.append(button);
    }
    this.markers.replaceChildren(markerFragment);
    this.element.classList.toggle('box-mode', this.mode === 'box');
    this.renderInfrastructure();
  }
  /** Kernel density surface for the current view, drawn at half resolution: each issue adds a soft disc
   * weighted by its sightings, and the summed intensity is coloured from faint blue (one report) to red. */
  renderHeat(width, height) {
    const scale = 0.5, w = Math.ceil(width * scale), h = Math.ceil(height * scale);
    const canvas = document.createElement('canvas');
    canvas.className = 'heat-layer'; canvas.width = w; canvas.height = h;
    canvas.style.cssText = `width:${width}px;height:${height}px`;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const metresPerPixel = 156543.03392 * Math.cos(this.center[1] * Math.PI / 180) / 2 ** this.zoom;
    this.heatRadius = Math.max(26, Math.min(90, 450 / metresPerPixel));
    const r = this.heatRadius * scale;
    for (const issue of this.issues) {
      const [x, y] = this.position(issue.geometry.coordinates).map(v => v * scale);
      if (x < -r || y < -r || x > w + r || y > h + r) continue;
      const weight = Math.min(1, 0.22 * (1 + Math.log2(issue.sightings_count || 1)));
      const disc = ctx.createRadialGradient(x, y, 0, x, y, r);
      disc.addColorStop(0, `rgba(0,0,0,${weight})`);
      disc.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = disc;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    }
    const image = ctx.getImageData(0, 0, w, h), px = image.data, ramp = this.heatRamp();
    for (let j = 3; j < px.length; j += 4) {
      const k = px[j] * 4;
      if (!k) continue;
      px[j - 3] = ramp[k]; px[j - 2] = ramp[k + 1]; px[j - 1] = ramp[k + 2]; px[j] = ramp[k + 3];
    }
    ctx.putImageData(image, 0, 0);
    return canvas;
  }
  heatRamp() {
    if (this.heatColours) return this.heatColours;
    const canvas = document.createElement('canvas'); canvas.width = 256; canvas.height = 1;
    const ctx = canvas.getContext('2d'), gradient = ctx.createLinearGradient(0, 0, 256, 0);
    for (const [stop, colour] of [[0, 'rgba(39,120,246,0)'], [0.12, 'rgba(39,120,246,.38)'], [0.35, 'rgba(39,184,246,.62)'], [0.6, 'rgba(255,180,82,.8)'], [0.85, 'rgba(250,101,117,.9)'], [1, 'rgba(255,214,222,.95)']]) gradient.addColorStop(stop, colour);
    ctx.fillStyle = gradient; ctx.fillRect(0, 0, 256, 1);
    return (this.heatColours = ctx.getImageData(0, 0, 256, 1).data);
  }
  /** In density mode a click lists the issues under the hot spot, like opening a cluster. */
  pickHeat(e) {
    const r = this.element.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    const ids = this.issues.filter(i => { const [px, py] = this.position(i.geometry.coordinates); return Math.hypot(px - x, py - y) <= this.heatRadius; }).map(i => i.issue_id);
    if (ids.length) this.onSelect(ids, ids.length === 1 ? 'issue' : 'cluster', e);
    else this.onEmpty();
  }
  preview(group, button) {
    if (this.motionFrame !== null) return;
    const first = group.items[0], multi = group.items.length > 1;
    const title = document.createElement('strong'); title.textContent = multi ? `${group.items.length} issues in this cluster` : first.issue_type;
    const location = document.createElement('span'); location.textContent = multi ? [...new Set(group.items.map(i => i.issue_type))].join(' · ') : first.address;
    const high = group.items.filter(i => i.severity === 'High').length;
    const meta = document.createElement('small'); meta.textContent = multi ? `${high ? `${high} high severity · ` : ''}Click to explore · Shift + click to select` : `${first.severity} priority · ${first.verification_status} · ~${first.location_radius_m}m`;
    this.tooltip.replaceChildren(title, location, meta);
    this.tooltip.hidden = false;
    const width = this.tooltip.offsetWidth, height = this.tooltip.offsetHeight;
    const x = Math.max(10, Math.min(this.element.clientWidth - width - 10, group.p[0] - width / 2));
    const y = group.p[1] - height - 29;
    this.tooltip.style.left = x + 'px';
    this.tooltip.style.top = (y < 120 ? Math.min(this.element.clientHeight - height - 10, group.p[1] + 28) : y) + 'px';
    button.setAttribute('aria-describedby', this.tooltip.id);
  }
  renderInfrastructure() {
    const layer = this.scene.querySelector('.infrastructure-layer'); layer.replaceChildren();
    const shown = this.assets.filter(a => this.layers.includes(a.type)), wards = this.layers.includes('Wards') ? this.boundaries : [];
    if (!shown.length && !wards.length) return;
    const w = this.element.clientWidth, h = this.element.clientHeight, inView = ([x, y], m = 0) => x > -m && x < w + m && y > -m && y < h + m;
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'asset-lines'); svg.setAttribute('width', w); svg.setAttribute('height', h);
    for (const ward of wards) {
      const path = document.createElementNS(ns, 'path'), active = this.activeArea === `ward:${ward.id}`;
      path.setAttribute('d', ward.rings.map(ring => `M${ring.map(c => this.position(c).map(v => v.toFixed(1)).join(',')).join('L')}Z`).join(''));
      path.setAttribute('class', `ward-outline ${active ? 'active' : ''}`);
      svg.append(path);
      const at = this.position(ward.labelAt);
      if (this.zoom < 11.5 || !inView(at, -20)) continue;
      // Ward labels are buttons: clicking one filters the whole workspace to that ward.
      const button = document.createElement('button');
      button.type = 'button'; button.className = `ward-label ${active ? 'active' : ''}`; button.style.cssText = `left:${at[0]}px;top:${at[1]}px`;
      button.innerHTML = `<b>${ward.id}</b>${this.zoom >= 12.5 ? `<span>${ward.name}</span>` : ''}`;
      button.setAttribute('aria-label', `Ward ${ward.id} ${ward.name}: filter to this ward`);
      button.onclick = e => { e.stopPropagation(); this.onArea?.(`ward:${ward.id}`); };
      layer.append(button);
    }
    const label = (asset, [x, y]) => {
      const el = document.createElement('span');
      el.className = `asset-label ${asset.type.toLowerCase()}`; el.style.cssText = `left:${x}px;top:${y}px`;
      el.append(document.createElement('i'), asset.name); layer.append(el);
    };
    for (const asset of shown) {
      if (asset.geometry.type !== 'Point') {
        const lines = asset.geometry.type === 'LineString' ? [asset.geometry.coordinates] : asset.geometry.coordinates;
        const visible = [];
        for (const coordinates of lines) {
          const points = coordinates.map(c => this.position(c));
          if (!points.some(p => inView(p, 200))) continue;
          const line = document.createElementNS(ns, 'polyline'); line.setAttribute('points', points.map(p => p.join(',')).join(' ')); svg.append(line);
          visible.push(...points.filter(p => inView(p, -60)));
        }
        if (visible.length) label(asset, visible.sort((a, b) => a[0] - b[0])[Math.floor(visible.length / 2)]);
      } else {
        const p = this.position(asset.geometry.coordinates);
        if (!inView(p, 40)) continue;
        // Names only once zoomed in; at city scale a dot per asset keeps the map readable.
        if (this.zoom >= 14.5) label(asset, p);
        else { const dot = document.createElement('span'); dot.className = `asset-dot ${asset.type.toLowerCase()}`; dot.style.cssText = `left:${p[0]}px;top:${p[1]}px`; layer.append(dot); }
      }
    }
    layer.prepend(svg);
  }
}
