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
  constructor(element, { onSelect, onEmpty, onMove, icon }) {
    Object.assign(this, { element, onSelect, onEmpty, onMove, icon, center: [-79.397, 43.661], zoom: 13, issues: [], selected: [], layers: [], mode: 'pan', drag: null, showHeat: false, tileCache: new Map(), motionFrame: null, renderFrame: null, lastWheel: 0, backdropTimer: null });
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
      pointercancel: () => { this.drag = null; this.box.style.display = 'none'; this.element.classList.remove('is-dragging'); },
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
        else if (e.key === 'Home') { e.preventDefault(); this.flyTo([-79.397, 43.661], 13); }
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
  pointerDown(e) {
    if (e.target.closest('button') || e.button !== 0) return;
    this.stopMotion(); this.render();
    this.element.setPointerCapture(e.pointerId);
    this.drag = { x: e.clientX, y: e.clientY, lastX: e.clientX, lastY: e.clientY, lastTime: performance.now(), vx: 0, vy: 0, center: project(this.center, this.zoom), moved: false };
    this.element.classList.add('is-dragging');
  }
  pointerMove(e) {
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
    if (!this.drag) return;
    const d = this.drag; this.drag = null; this.box.style.display = 'none';
    this.element.classList.remove('is-dragging');
    cancelAnimationFrame(this.renderFrame); this.renderFrame = null;
    if (this.mode === 'box' && d.moved) {
      const r = this.element.getBoundingClientRect(), x1 = Math.min(d.x, e.clientX) - r.left, x2 = Math.max(d.x, e.clientX) - r.left, y1 = Math.min(d.y, e.clientY) - r.top, y2 = Math.max(d.y, e.clientY) - r.top;
      const ids = this.issues.filter(i => { const [x, y] = this.position(i.geometry.coordinates); return x >= x1 && x <= x2 && y >= y1 && y <= y2; }).map(i => i.issue_id);
      this.onSelect(ids, 'multi', e);
    } else if (!d.moved) this.onEmpty();
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
    const visible = this.issues.map(i => ({ issue: i, p: this.position(i.geometry.coordinates) })).filter(({ p }) => p[0] > -25 && p[0] < width + 25 && p[1] > -25 && p[1] < height + 25);
    const groups = [];
    for (const point of visible) {
      const group = groups.find(g => Math.hypot(g.p[0] - point.p[0], g.p[1] - point.p[1]) < (this.zoom < 14 ? 48 : 25));
      if (group) group.items.push(point.issue); else groups.push({ p: point.p, items: [point.issue] });
    }
    const oldMarkers = new Map([...this.markers.children].map(b => [b.dataset.key, b]));
    const markerFragment = document.createDocumentFragment();
    // A selected issue gets an uncertainty area rather than implying an exact location.
    if (this.selected.length === 1) {
      const issue = this.issues.find(i => i.issue_id === this.selected[0]);
      if (issue) {
        const [x, y] = this.position(issue.geometry.coordinates);
        const radius = Math.max(14, issue.location_radius_m / (156543.03392 * Math.cos(issue.geometry.coordinates[1] * Math.PI / 180) / 2 ** this.zoom));
        const area = document.createElement('div'); area.className = 'uncertainty-area';
        area.style.cssText = `left:${x}px;top:${y}px;width:${radius * 2}px;height:${radius * 2}px`;
        area.setAttribute('aria-label', `Approximate location within ${issue.location_radius_m} metres`);
        markerFragment.append(area);
      }
    }
    for (const group of groups) {
      const first = group.items[0], multi = group.items.length > 1, key = group.items.map(i => i.issue_id).join(',');
      const button = oldMarkers.get(key) || document.createElement('button');
      button.dataset.key = key;
      button.className = `map-pin ${multi ? 'cluster' : ''} ${group.items.some(i => this.selected.includes(i.issue_id)) ? 'selected' : ''} ${this.showHeat ? 'heat-pin' : ''}`;
      button.style.cssText = `left:${group.p[0]}px;top:${group.p[1]}px;--pin:${this.color(first.issue_type)}`;
      button.innerHTML = multi ? `<span>${group.items.length}</span>` : this.icon(first.issue_type);
      const label = multi ? `${group.items.length} issues · click to explore` : `${first.issue_type} · ${first.address}`;
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
  preview(group, button) {
    if (this.motionFrame !== null) return;
    const first = group.items[0], multi = group.items.length > 1;
    const title = document.createElement('strong'); title.textContent = multi ? `${group.items.length} issues in this cluster` : first.issue_type;
    const location = document.createElement('span'); location.textContent = multi ? [...new Set(group.items.map(i => i.issue_type))].join(' · ') : first.address;
    const meta = document.createElement('small'); meta.textContent = multi ? 'Click to explore · Shift + click to select' : `${first.severity} priority · ${first.verification_status} · ~${first.location_radius_m}m`;
    this.tooltip.replaceChildren(title, location, meta);
    this.tooltip.hidden = false;
    const width = this.tooltip.offsetWidth, height = this.tooltip.offsetHeight;
    const x = Math.max(10, Math.min(this.element.clientWidth - width - 10, group.p[0] - width / 2));
    const y = group.p[1] - height - 29;
    this.tooltip.style.left = x + 'px';
    this.tooltip.style.top = (y < 120 ? Math.min(this.element.clientHeight - height - 10, group.p[1] + 28) : y) + 'px';
    button.setAttribute('aria-describedby', this.tooltip.id);
  }
  color(type) { return { Pothole: '#fa6575', 'Sidewalk damage': '#ffb452', Graffiti: '#ba80f6', Litter: '#25d5ac', Flooding: '#4ea8ff', Other: '#9daec3' }[type]; }
  renderInfrastructure() {
    const layer = this.scene.querySelector('.infrastructure-layer'); layer.replaceChildren();
    const assets = [['TTC', 'Union', -79.38, 43.645], ['TTC', 'Spadina', -79.403, 43.667], ['TTC', 'Osgoode', -79.386, 43.65], ['Schools', 'U of T', -79.396, 43.663], ['Schools', 'TMU', -79.379, 43.657], ['Roads', 'Gardiner Expressway', -79.40, 43.637]];
    for (const [type, name, lng, lat] of assets) {
      if (!this.layers.includes(type)) continue;
      const [x, y] = this.position([lng, lat]), el = document.createElement('span');
      el.className = 'asset-label'; el.style.cssText = `left:${x}px;top:${y}px`; el.textContent = `${type === 'TTC' ? 'Ⓜ' : '◇'} ${name}`; layer.append(el);
    }
  }
}
