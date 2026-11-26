import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

/**
 * DEMO MODE - "Explore any place".
 * Type a place name -> fly to it in an interactive 3D globe-style scene (real terrain relief, satellite imagery,
 * extruded 3D buildings) with a distance / area measuring tool.
 * Data comes from public map services (Esri World Imagery, AWS Terrain Tiles, OpenFreeMap buildings, OSM Nominatim);
 * it needs internet and is NOT produced by our reconstruction pipeline. It is labelled as such in the UI.
 */
const PRESETS: Array<{ name: string; q: string; lon: number; lat: number; zoom: number; pitch: number }> = [
  { name: 'Taj Mahal', q: 'Taj Mahal, Agra', lon: 78.0421, lat: 27.1751, zoom: 16.6, pitch: 70 },
  { name: 'Sigiriya', q: 'Sigiriya Rock', lon: 80.7603, lat: 7.957, zoom: 15.8, pitch: 72 },
  { name: 'Burj Khalifa', q: 'Burj Khalifa, Dubai', lon: 55.2744, lat: 25.1972, zoom: 16.2, pitch: 72 },
  { name: 'Eiffel Tower', q: 'Eiffel Tower, Paris', lon: 2.2945, lat: 48.8584, zoom: 16.8, pitch: 70 },
  { name: 'Grand Canyon', q: 'Grand Canyon Village', lon: -112.1129, lat: 36.0544, zoom: 12.5, pitch: 75 },
  { name: 'Mangalore', q: 'Mangalore', lon: 74.856, lat: 12.9141, zoom: 14.5, pitch: 65 },
];

type LngLat = [number, number];
type Mode = 'off' | 'distance' | 'area';

const R = 6371008.8;
const rad = (d: number) => (d * Math.PI) / 180;
function haversine(a: LngLat, b: LngLat) {
  const dLat = rad(b[1] - a[1]);
  const dLon = rad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function polygonArea(pts: LngLat[]) {
  if (pts.length < 3) return 0;
  // spherical excess approximation on an equirectangular projection around the centroid (fine for site-scale areas)
  const lat0 = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const xy = pts.map((p) => [rad(p[0]) * R * Math.cos(rad(lat0)), rad(p[1]) * R]);
  let s = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i];
    const [x2, y2] = xy[(i + 1) % xy.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2;
}
const fmtLen = (m: number, imperial: boolean) =>
  imperial ? (m * 3.28084 > 5280 ? `${(m / 1609.344).toFixed(2)} mi` : `${(m * 3.28084).toFixed(0)} ft`)
           : (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${m.toFixed(m < 100 ? 1 : 0)} m`);
const fmtArea = (m2: number, imperial: boolean) =>
  imperial ? `${(m2 * 10.7639).toLocaleString(undefined, { maximumFractionDigits: 0 })} ft²`
           : (m2 >= 1e6 ? `${(m2 / 1e6).toFixed(3)} km²` : `${m2.toLocaleString(undefined, { maximumFractionDigits: 0 })} m²`);

export const ExploreDemo: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const modeRef = useRef<Mode>('off');
  const ptsRef = useRef<LngLat[]>([]);
  const spinRef = useRef<number | null>(null);

  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('Loading map…');
  const [mode, setMode] = useState<Mode>('off');
  const [pts, setPts] = useState<LngLat[]>([]);
  const [imperial, setImperial] = useState(false);
  const [exag, setExag] = useState(1.6);
  const [satellite, setSatellite] = useState(true);
  const [buildings, setBuildings] = useState(true);
  const [orbiting, setOrbiting] = useState(false);
  const [place, setPlace] = useState('Taj Mahal');
  const [elevs, setElevs] = useState<number[]>([]);

  modeRef.current = mode;
  ptsRef.current = pts;

  // ---------------------------------------------------------------- map setup
  useEffect(() => {
    if (!box.current) return;
    const map = new maplibregl.Map({
      container: box.current,
      center: [PRESETS[0].lon, PRESETS[0].lat],
      zoom: PRESETS[0].zoom,
      pitch: PRESETS[0].pitch,
      bearing: -20,
      maxPitch: 85,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sky: { 'sky-color': '#9fc5ee', 'horizon-color': '#e6eef7', 'fog-color': '#e6eef7', 'sky-horizon-blend': 0.6, 'horizon-fog-blend': 0.6, 'fog-ground-blend': 0.3 } as any,
        sources: {
          sat: { type: 'raster', tileSize: 256, maxzoom: 19,
            tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
            attribution: 'Imagery © Esri, Maxar, Earthstar Geographics' },
          osm: { type: 'raster', tileSize: 256, maxzoom: 19,
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], attribution: '© OpenStreetMap contributors' },
          dem: { type: 'raster-dem', encoding: 'terrarium', tileSize: 256, maxzoom: 15,
            tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            attribution: 'Terrain: Mapzen / AWS Open Data' },
          omt: { type: 'vector', url: 'https://tiles.openfreemap.org/planet', attribution: 'Buildings © OpenFreeMap, OpenStreetMap' },
        },
        layers: [
          { id: 'osm', type: 'raster', source: 'osm', layout: { visibility: 'none' } },
          { id: 'sat', type: 'raster', source: 'sat' },
          { id: 'bld', type: 'fill-extrusion', source: 'omt', 'source-layer': 'building', minzoom: 14,
            paint: {
              'fill-extrusion-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 6], 0, '#e8e2d6', 40, '#d6dbe6', 150, '#b9c3d6'],
              'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 6],
              'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
              'fill-extrusion-opacity': 0.82,
            } },
        ],
        terrain: { source: 'dem', exaggeration: 1.6 },
      } as any,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

    map.on('load', () => {
      map.addSource('meas', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'meas-fill', type: 'fill', source: 'meas', filter: ['==', '$type', 'Polygon'], paint: { 'fill-color': '#A7ED79', 'fill-opacity': 0.25 } });
      map.addLayer({ id: 'meas-line-casing', type: 'line', source: 'meas', filter: ['==', '$type', 'LineString'], paint: { 'line-color': '#171A20', 'line-width': 7 } });
      map.addLayer({ id: 'meas-line', type: 'line', source: 'meas', filter: ['==', '$type', 'LineString'], paint: { 'line-color': '#A7ED79', 'line-width': 3.5 } });
      setStatus('Ready');
    });
    map.on('error', (e: any) => {
      const m = String(e?.error?.message || '');
      if (/Failed to fetch|NetworkError|Load failed|ERR_/.test(m)) setStatus('Map data could not be loaded - check the internet connection.');
    });
    map.on('click', (e) => {
      if (modeRef.current === 'off') return;
      setPts([...ptsRef.current, [e.lngLat.lng, e.lngLat.lat]]);
    });
    map.on('mousemove', () => { map.getCanvas().style.cursor = modeRef.current === 'off' ? '' : 'crosshair'; });
    const stopSpin = () => { if (spinRef.current) { cancelAnimationFrame(spinRef.current); spinRef.current = null; setOrbiting(false); } };
    map.on('mousedown', stopSpin);
    map.on('wheel', stopSpin);
    return () => { stopSpin(); map.remove(); mapRef.current = null; };
  }, []);

  // ---------------------------------------------------------------- layers
  useEffect(() => {
    const m = mapRef.current; if (!m || !m.isStyleLoaded()) return;
    m.setLayoutProperty('sat', 'visibility', satellite ? 'visible' : 'none');
    m.setLayoutProperty('osm', 'visibility', satellite ? 'none' : 'visible');
  }, [satellite, status]);
  useEffect(() => {
    const m = mapRef.current; if (!m || !m.isStyleLoaded()) return;
    m.setLayoutProperty('bld', 'visibility', buildings ? 'visible' : 'none');
  }, [buildings, status]);
  useEffect(() => {
    const m = mapRef.current; if (!m || !m.isStyleLoaded()) return;
    m.setTerrain({ source: 'dem', exaggeration: exag });
  }, [exag, status]);

  // ---------------------------------------------------------------- measuring: redraw markers / line / elevations
  useEffect(() => {
    const m = mapRef.current; if (!m) return;
    markers.current.forEach((x) => x.remove());
    markers.current = pts.map((p, i) => {
      const el = document.createElement('div');
      el.style.cssText = 'width:20px;height:20px;border-radius:50%;background:#A7ED79;border:3px solid #171A20;color:#171A20;font:700 10px/14px system-ui;text-align:center;box-shadow:0 1px 6px rgba(0,0,0,.5)';
      el.textContent = String(i + 1);
      return new maplibregl.Marker({ element: el }).setLngLat(p).addTo(m);
    });
    const src = m.getSource('meas') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      const feats: any[] = [];
      if (pts.length >= 2) {
        const line = mode === 'area' && pts.length >= 3 ? [...pts, pts[0]] : pts;
        feats.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: line } });
      }
      if (mode === 'area' && pts.length >= 3) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...pts, pts[0]]] } });
      src.setData({ type: 'FeatureCollection', features: feats });
    }
    try { setElevs(pts.map((p) => m.queryTerrainElevation(p as any) ?? NaN)); } catch { setElevs([]); }
  }, [pts, mode]);

  // ---------------------------------------------------------------- actions
  const flyTo = (lon: number, lat: number, zoom: number, pitch = 68, label?: string) => {
    mapRef.current?.flyTo({ center: [lon, lat], zoom, pitch, bearing: -25, speed: 0.9, curve: 1.6, essential: true });
    if (label) setPlace(label);
    setPts([]);
  };
  const search = async (text: string) => {
    if (!text.trim()) return;
    setStatus('Searching…');
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=${encodeURIComponent(text)}`, { headers: { Accept: 'application/json' } });
      const j = await r.json();
      if (!j.length) { setStatus(`No place found for "${text}".`); return; }
      const hit = j[0];
      const bb = hit.boundingbox?.map(Number); // [s, n, w, e]
      let zoom = 15.5;
      if (bb) {
        const span = Math.max(Math.abs(bb[1] - bb[0]), Math.abs(bb[3] - bb[2]), 0.0015);
        zoom = Math.max(9, Math.min(17.5, Math.log2(360 / span) - 1.2));
      }
      flyTo(Number(hit.lon), Number(hit.lat), zoom, zoom > 13 ? 68 : 55, String(hit.display_name).split(',').slice(0, 2).join(','));
      setStatus('Ready');
    } catch {
      setStatus('Search needs an internet connection.');
    }
  };
  const orbit = () => {
    const m = mapRef.current; if (!m) return;
    if (spinRef.current) { cancelAnimationFrame(spinRef.current); spinRef.current = null; setOrbiting(false); return; }
    setOrbiting(true);
    let last = performance.now();
    const tick = (t: number) => {
      m.setBearing(m.getBearing() + ((t - last) / 1000) * 8);
      last = t;
      spinRef.current = requestAnimationFrame(tick);
    };
    spinRef.current = requestAnimationFrame(tick);
  };
  const setTool = (t: Mode) => { setMode(mode === t ? 'off' : t); setPts([]); };

  // ---------------------------------------------------------------- numbers
  let total = 0;
  const legs: number[] = [];
  for (let i = 1; i < pts.length; i++) { const d = haversine(pts[i - 1], pts[i]); legs.push(d); total += d; }
  const closed = mode === 'area' && pts.length >= 3 ? haversine(pts[pts.length - 1], pts[0]) : 0;
  const perimeter = total + closed;
  const area = mode === 'area' ? polygonArea(pts) : 0;
  const fin = elevs.filter((e) => Number.isFinite(e));
  const climb = elevs.reduce((s, e, i) => (i > 0 && Number.isFinite(e) && Number.isFinite(elevs[i - 1]) && e > elevs[i - 1] ? s + e - elevs[i - 1] : s), 0);

  const chip = (active: boolean): React.CSSProperties => ({
    padding: '7px 11px', fontSize: 12, fontWeight: 700, cursor: 'pointer', borderRadius: 4,
    border: active ? '1px solid #A7ED79' : '1px solid rgba(255,255,255,.18)',
    background: active ? 'rgba(167,237,121,.2)' : 'rgba(23,26,32,.82)', color: active ? '#A7ED79' : '#F7F8FA',
  });
  const panel: React.CSSProperties = { background: 'rgba(23,26,32,.88)', border: '1px solid rgba(255,255,255,.14)', borderRadius: 6, color: '#F7F8FA', backdropFilter: 'blur(6px)' };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 520, background: '#0d1117' }}>
      <div ref={box} style={{ position: 'absolute', inset: 0 }} data-testid="explore-map" />

      {/* Top bar: search + presets */}
      <div style={{ position: 'absolute', top: 12, left: 12, right: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-start', pointerEvents: 'none' }}>
        <form onSubmit={(e) => { e.preventDefault(); search(query); }} style={{ ...panel, padding: 6, display: 'flex', gap: 6, pointerEvents: 'auto' }}>
          <input
            value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Type any place - e.g. Machu Picchu, Mangalore, Eiffel Tower"
            style={{ width: 330, maxWidth: '55vw', background: '#0d1117', color: '#F7F8FA', border: '1px solid rgba(255,255,255,.2)', borderRadius: 4, padding: '8px 10px', fontSize: 13 }}
          />
          <button type="submit" style={{ ...chip(true), padding: '8px 14px' }}>Generate 3D</button>
        </form>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', pointerEvents: 'auto' }}>
          {PRESETS.map((p) => (
            <button key={p.name} style={chip(place === p.name)} onClick={() => flyTo(p.lon, p.lat, p.zoom, p.pitch, p.name)}>{p.name}</button>
          ))}
        </div>
        <button style={{ ...chip(false), marginLeft: 'auto', pointerEvents: 'auto' }} onClick={onClose}>✕ Close demo</button>
      </div>

      {/* Left tool column */}
      <div style={{ position: 'absolute', top: 100, left: 12, display: 'flex', flexDirection: 'column', gap: 6, width: 190 }}>
        <div style={{ ...panel, padding: 10, fontSize: 12 }}>
          <div style={{ fontWeight: 800, marginBottom: 2 }}>{place}</div>
          <div style={{ color: '#BAC0CB' }}>{status}</div>
        </div>
        <button style={chip(mode === 'distance')} onClick={() => setTool('distance')}>📏 Measure distance</button>
        <button style={chip(mode === 'area')} onClick={() => setTool('area')}>⬚ Measure area</button>
        <button style={chip(orbiting)} onClick={orbit}>⟳ {orbiting ? 'Stop orbit' : 'Orbit around'}</button>
        <button style={chip(satellite)} onClick={() => setSatellite(!satellite)}>{satellite ? '🛰 Satellite' : '🗺 Street map'}</button>
        <button style={chip(buildings)} onClick={() => setBuildings(!buildings)}>🏢 3D buildings {buildings ? 'on' : 'off'}</button>
        <button style={chip(imperial)} onClick={() => setImperial(!imperial)}>Units: {imperial ? 'feet / miles' : 'metres / km'}</button>
        <div style={{ ...panel, padding: 10, fontSize: 12 }}>
          <label style={{ display: 'block', marginBottom: 4 }}>Terrain height ×{exag.toFixed(1)}</label>
          <input type="range" min={1} max={3} step={0.1} value={exag} onChange={(e) => setExag(Number(e.target.value))} style={{ width: '100%' }} />
        </div>
        <div style={{ ...panel, padding: 10, fontSize: 11, color: '#BAC0CB', lineHeight: 1.5 }}>
          Drag = pan · right-drag / Ctrl-drag = tilt &amp; rotate · scroll = zoom
        </div>
      </div>

      {/* Measurement readout */}
      {mode !== 'off' && (
        <div style={{ ...panel, position: 'absolute', top: 100, right: 12, width: 250, padding: 12, fontSize: 12 }} data-testid="measure-panel">
          <div style={{ fontWeight: 800, marginBottom: 6 }}>{mode === 'distance' ? 'Distance' : 'Area'} measurement</div>
          {pts.length === 0 && <div style={{ color: '#BAC0CB' }}>Click on the map to place points.</div>}
          {mode === 'distance' && pts.length >= 2 && (
            <>
              <div style={{ fontSize: 26, fontWeight: 800, color: '#A7ED79' }} data-testid="measure-total">{fmtLen(total, imperial)}</div>
              <div style={{ color: '#BAC0CB', margin: '4px 0' }}>{legs.length} segment{legs.length > 1 ? 's' : ''}</div>
              {legs.length > 1 && legs.map((l, i) => <div key={i} style={{ display: 'flex', justifyContent: 'space-between' }}><span>{i + 1} → {i + 2}</span><span>{fmtLen(l, imperial)}</span></div>)}
            </>
          )}
          {mode === 'area' && pts.length >= 3 && (
            <>
              <div style={{ fontSize: 26, fontWeight: 800, color: '#A7ED79' }} data-testid="measure-total">{fmtArea(area, imperial)}</div>
              <div style={{ color: '#BAC0CB', margin: '4px 0' }}>Perimeter {fmtLen(perimeter, imperial)}</div>
            </>
          )}
          {pts.length >= 2 && fin.length >= 2 && (
            <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid rgba(255,255,255,.14)', color: '#BAC0CB' }}>
              Ground elevation {fmtLen(Math.min(...fin), imperial)} – {fmtLen(Math.max(...fin), imperial)}<br />
              Total climb {fmtLen(climb, imperial)}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
            <button style={chip(false)} disabled={!pts.length} onClick={() => setPts(pts.slice(0, -1))}>Undo</button>
            <button style={chip(false)} disabled={!pts.length} onClick={() => setPts([])}>Clear</button>
            <button style={chip(false)} onClick={() => { setMode('off'); }}>Done</button>
          </div>
          <div style={{ color: '#8a919e', fontSize: 10, marginTop: 8 }}>Great-circle distance on the map surface (horizontal). Accuracy depends on the map data.</div>
        </div>
      )}

      <div style={{ position: 'absolute', bottom: 12, left: '50%', transform: 'translateX(-50%)', ...panel, padding: '5px 12px', fontSize: 11, color: '#BAC0CB' }}>
        DEMO MODE · public map data (Esri imagery, AWS terrain, OpenStreetMap buildings) · not generated by the drone-video pipeline
      </div>
    </div>
  );
};
