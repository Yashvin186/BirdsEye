import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Ruler, Layers, Maximize2, ZoomIn, ZoomOut, Download, Compass } from 'lucide-react';

interface MapViewerProps {
  files: Record<string, { filename: string; size_bytes: number; format: string; download_url: string }>;
  qualityReport?: any;
}

type Layer = 'ortho' | 'height' | 'blend';
interface Pt { x: number; y: number }   // image pixel coordinates

const niceLength = (m: number) => {
  const p = Math.pow(10, Math.floor(Math.log10(m)));
  const f = m / p;
  return (f >= 5 ? 5 : f >= 2 ? 2 : 1) * p;
};

/**
 * Interactive 2D map: the orthomosaic (a true top-down, distortion-free picture of the site) with pan / zoom,
 * a height-map overlay, a distance measuring tool, scale bar and north arrow. Distances are in metres when the
 * project was georeferenced from the drone's GPS log; otherwise they are labelled as relative units.
 */
export const MapViewer: React.FC<MapViewerProps> = ({ files, qualityReport }) => {
  const orthoUrl = files['orthomosaic.jpg']?.download_url;
  const dsmUrl = files['dsm_heightmap.png']?.download_url;
  const geo = qualityReport?.georeferencing;
  const groundW: number | undefined = geo?.ground_size_m?.[0];
  const gsdCm: number | undefined = geo?.ground_sample_distance_cm;
  const metric = Boolean(groundW && geo?.status && String(geo.status).toLowerCase().includes('gps'));

  const boxRef = useRef<HTMLDivElement>(null);
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null);
  const [view, setView] = useState({ s: 1, x: 0, y: 0 });
  const [layer, setLayer] = useState<Layer>('ortho');
  const [opacity, setOpacity] = useState(0.55);
  const [measure, setMeasure] = useState(false);
  const [pts, setPts] = useState<Pt[]>([]);
  const [hover, setHover] = useState<Pt | null>(null);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);

  const mPerPx = metric && nat ? (groundW as number) / nat.w : undefined;

  const fit = useCallback(() => {
    const box = boxRef.current;
    if (!box || !nat) return;
    const s = Math.min(box.clientWidth / nat.w, box.clientHeight / nat.h) * 0.95;
    setView({ s, x: (box.clientWidth - nat.w * s) / 2, y: (box.clientHeight - nat.h * s) / 2 });
  }, [nat]);

  useEffect(() => { fit(); }, [fit]);
  useEffect(() => {
    const onResize = () => fit();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [fit]);

  const toImage = (cx: number, cy: number): Pt => {
    const r = boxRef.current!.getBoundingClientRect();
    return { x: (cx - r.left - view.x) / view.s, y: (cy - r.top - view.y) / view.s };
  };

  const zoomAt = (factor: number, cx?: number, cy?: number) => {
    const box = boxRef.current;
    if (!box) return;
    const r = box.getBoundingClientRect();
    const px = (cx ?? r.left + r.width / 2) - r.left;
    const py = (cy ?? r.top + r.height / 2) - r.top;
    setView(v => {
      const s = Math.min(Math.max(v.s * factor, 0.05), 40);
      const k = s / v.s;
      return { s, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
    });
  };

  const onWheel = (e: React.WheelEvent) => zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX, e.clientY);
  const onDown = (e: React.PointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
  };
  const onMove = (e: React.PointerEvent) => {
    if (drag.current) {
      const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) drag.current.moved = true;
      if (drag.current.moved) setView(v => ({ ...v, x: drag.current!.vx + dx, y: drag.current!.vy + dy }));
    }
    if (nat) setHover(toImage(e.clientX, e.clientY));
  };
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (d && !d.moved && measure && nat) {
      const p = toImage(e.clientX, e.clientY);
      if (p.x >= 0 && p.y >= 0 && p.x <= nat.w && p.y <= nat.h) setPts(prev => (prev.length >= 2 ? [p] : [...prev, p]));
    }
  };

  const dist = useMemo(() => {
    if (pts.length < 2) return null;
    const px = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
    return mPerPx ? { v: px * mPerPx, unit: 'm' } : { v: px, unit: 'px (relative)' };
  }, [pts, mPerPx]);

  // Scale bar
  const barM = mPerPx ? niceLength((mPerPx / view.s) * 120) : 0;
  const barPx = mPerPx ? barM / (mPerPx / view.s) : 0;

  if (!orthoUrl) {
    return (
      <div style={{ padding: 24, color: '#4D5258', fontSize: 14 }}>
        <strong>2D map not available for this project.</strong>
        <div style={{ marginTop: 6 }}>
          The 2D map (orthomosaic) is produced when the video is a straight-down survey flight over an area.
          Object / orbit videos are shown in the 3D viewer.
        </div>
      </div>
    );
  }

  const btn: React.CSSProperties = {
    background: 'rgba(23,26,32,0.88)', color: '#fff', border: '1px solid rgba(255,255,255,0.18)', borderRadius: 6,
    padding: '6px 9px', fontSize: 12, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
  };
  const on: React.CSSProperties = { ...btn, background: '#0b6bcb', borderColor: '#5aa9ff' };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: '#12151a', overflow: 'hidden' }}>
      <div
        ref={boxRef}
        onWheel={onWheel}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={() => setHover(null)}
        style={{ position: 'absolute', inset: 0, cursor: measure ? 'crosshair' : drag.current ? 'grabbing' : 'grab', touchAction: 'none' }}
      >
        <div style={{ position: 'absolute', left: 0, top: 0, width: nat?.w ?? 0, height: nat?.h ?? 0,
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.s})`, transformOrigin: '0 0' }}>
          {(layer === 'ortho' || layer === 'blend') && (
            <img src={orthoUrl} alt="Orthomosaic" draggable={false}
              onLoad={e => setNat({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
              style={{ position: 'absolute', left: 0, top: 0, width: nat?.w, height: nat?.h, imageRendering: view.s > 3 ? 'pixelated' : 'auto', userSelect: 'none' }} />
          )}
          {layer === 'height' && dsmUrl && (
            <img src={dsmUrl} alt="Height map" draggable={false} style={{ position: 'absolute', left: 0, top: 0, width: nat?.w, height: nat?.h, imageRendering: 'auto' }} />
          )}
          {layer === 'blend' && dsmUrl && (
            <img src={dsmUrl} alt="Height overlay" draggable={false} style={{ position: 'absolute', left: 0, top: 0, width: nat?.w, height: nat?.h, opacity, mixBlendMode: 'normal' }} />
          )}
          {nat && (
            <svg width={nat.w} height={nat.h} style={{ position: 'absolute', left: 0, top: 0, pointerEvents: 'none', overflow: 'visible' }}>
              {pts.length === 2 && <line x1={pts[0].x} y1={pts[0].y} x2={pts[1].x} y2={pts[1].y} stroke="#ffeb3b" strokeWidth={2.5 / view.s} />}
              {pts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={5 / view.s} fill={i === 0 ? '#ff4081' : '#00e676'} stroke="#fff" strokeWidth={1.5 / view.s} />)}
            </svg>
          )}
        </div>
      </div>

      {/* Toolbar */}
      <div style={{ position: 'absolute', top: 12, left: 12, display: 'flex', gap: 6, flexWrap: 'wrap', maxWidth: 'calc(100% - 24px)' }}>
        <button style={layer === 'ortho' ? on : btn} onClick={() => setLayer('ortho')}><Layers size={14} /> Map</button>
        {dsmUrl && <button style={layer === 'height' ? on : btn} onClick={() => setLayer('height')}>Height map</button>}
        {dsmUrl && <button style={layer === 'blend' ? on : btn} onClick={() => setLayer('blend')}>Overlay</button>}
        {layer === 'blend' && (
          <input type="range" min={0.1} max={0.9} step={0.05} value={opacity} onChange={e => setOpacity(parseFloat(e.target.value))} title="Overlay strength" />
        )}
        <button style={measure ? on : btn} onClick={() => { setMeasure(m => !m); setPts([]); }}><Ruler size={14} /> Measure</button>
        <button style={btn} onClick={() => zoomAt(1.4)} title="Zoom in"><ZoomIn size={14} /></button>
        <button style={btn} onClick={() => zoomAt(1 / 1.4)} title="Zoom out"><ZoomOut size={14} /></button>
        <button style={btn} onClick={fit} title="Fit to screen"><Maximize2 size={14} /></button>
        <a style={{ ...btn, textDecoration: 'none' }} href={orthoUrl} download="orthomosaic.jpg"><Download size={14} /> Map JPG</a>
      </div>

      {/* Info panel */}
      <div style={{ position: 'absolute', top: 12, right: 12, background: 'rgba(23,26,32,0.88)', color: '#e8eaee', border: '1px solid rgba(255,255,255,0.15)',
        borderRadius: 6, padding: '8px 12px', fontSize: 12, lineHeight: 1.5, maxWidth: 260 }}>
        <div style={{ fontWeight: 700, marginBottom: 2 }}>Orthomosaic map</div>
        {metric ? (
          <>
            <div>Site: {geo.ground_size_m[0]} × {geo.ground_size_m[1]} m</div>
            {gsdCm !== undefined && <div>Detail: {gsdCm} cm per pixel</div>}
            <div>Scale from drone GPS (±{Number(geo.rmse_error ?? 0).toFixed(1)} m path fit)</div>
          </>
        ) : (
          <div style={{ color: '#ffd666' }}>No GPS flight log: distances are relative, not metres. Add the drone's .SRT file before processing.</div>
        )}
        {qualityReport?.coverage?.recommendation && <div style={{ marginTop: 6, color: '#9ad', fontSize: 11 }}>{qualityReport.coverage.recommendation}</div>}
        {measure && <div style={{ marginTop: 4, color: '#9ad' }}>{pts.length === 0 ? 'Click the first point' : pts.length === 1 ? 'Click the second point' : 'Click to start a new line'}</div>}
        {dist && <div style={{ marginTop: 4, fontSize: 14, color: '#00e676', fontWeight: 700 }}>{dist.v.toFixed(dist.unit === 'm' ? 1 : 0)} {dist.unit}</div>}
      </div>

      {/* Bottom-left: scale bar + coordinates */}
      <div style={{ position: 'absolute', left: 12, bottom: 12, color: '#fff', fontSize: 12, textShadow: '0 1px 3px #000' }}>
        {metric && (
          <div style={{ marginBottom: 6 }}>
            <div style={{ width: barPx, height: 6, borderLeft: '2px solid #fff', borderRight: '2px solid #fff', borderBottom: '2px solid #fff' }} />
            <div>{barM >= 1000 ? `${barM / 1000} km` : `${barM} m`}</div>
          </div>
        )}
        {hover && nat && hover.x >= 0 && hover.y >= 0 && hover.x <= nat.w && hover.y <= nat.h && (
          <div style={{ background: 'rgba(23,26,32,0.8)', padding: '3px 8px', borderRadius: 4 }}>
            {mPerPx
              ? `${(hover.x * mPerPx).toFixed(1)} m east · ${((nat.h - hover.y) * mPerPx).toFixed(1)} m north of the map's SW corner`
              : `x ${hover.x.toFixed(0)}, y ${hover.y.toFixed(0)} px`}
          </div>
        )}
      </div>

      {/* North arrow (the map is oriented north-up when GPS-referenced) */}
      {metric && (
        <div style={{ position: 'absolute', right: 14, bottom: 14, color: '#fff', textAlign: 'center', fontSize: 11, textShadow: '0 1px 3px #000' }}>
          <Compass size={26} />
          <div style={{ fontWeight: 700 }}>N ↑</div>
        </div>
      )}
      {layer !== 'ortho' && dsmUrl && (
        <div style={{ position: 'absolute', left: '50%', bottom: 14, transform: 'translateX(-50%)', color: '#fff', fontSize: 11, textAlign: 'center', textShadow: '0 1px 3px #000' }}>
          <div style={{ width: 180, height: 8, borderRadius: 4, background: 'linear-gradient(90deg,#30123b,#4662d7,#36aaf9,#1ae4b6,#72fe5e,#c7ef34,#faba39,#f66b19,#ca2a04,#7a0403)' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>low</span><span>height (relative)</span><span>high</span></div>
        </div>
      )}
    </div>
  );
};
