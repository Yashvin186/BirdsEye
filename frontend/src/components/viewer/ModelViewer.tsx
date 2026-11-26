import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import {
  RotateCcw,
  Maximize,
  Grid,
  Compass,
  Box,
  Info,
  Camera,
  Sun,
  Ruler,
  Sliders,
  Layers,
  Palette,
  Eye,
  Download,
  Check,
  X,
  Play,
  Pause,
  RotateCw,
  Minimize,
  Link2,
  Map as MapIcon
} from 'lucide-react';

interface Props {
  projectId: string;
  files: Record<string, { filename: string; size_bytes: number; format: string; download_url: string }>;
  qualityReport?: any;
}

interface CameraPose {
  id: number;
  name: string;
  position: [number, number, number];
  direction: [number, number, number];
  quaternion?: [number, number, number, number];
}

type DisplayMode = 'points' | 'solid' | 'wireframe';
type ColorMode = 'rgb' | 'elevation' | 'normals';

export const ModelViewer: React.FC<Props> = ({ projectId, files, qualityReport }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const loadedFileRef = useRef<string | null>(null);

  // Viewer modes
  const [displayMode, setDisplayMode] = useState<DisplayMode>('solid');
  const [colorMode, setColorMode] = useState<ColorMode>('rgb');
  const [pointSize, setPointSize] = useState<number>(3.0);
  const [sizeAttenuation, setSizeAttenuation] = useState<boolean>(true);

  // Toggles
  const [showGrid, setShowGrid] = useState<boolean>(true);
  const [showAxes, setShowAxes] = useState<boolean>(true);
  const [showBox, setShowBox] = useState<boolean>(false);
  const [showCameras, setShowCameras] = useState<boolean>(true);
  const [measureMode, setMeasureMode] = useState<boolean>(false);
  const [showLightingControls, setShowLightingControls] = useState<boolean>(false);

  // Sunlight angles
  const [sunAzimuth, setSunAzimuth] = useState<number>(45);
  const [sunElevation, setSunElevation] = useState<number>(55);

  // Stats & Status
  const [rawDims, setRawDims] = useState<{ isCloud: boolean; sx: number; sz: number; sy: number; elev: number } | null>(null);
  const [stats, setStats] = useState<{
    points: number;
    faces: number;
    bounds: string;
    elevationSpan: string;
    minZ: number;
    maxZ: number;
  }>({
    points: 0,
    faces: 0,
    bounds: '--',
    elevationSpan: '--',
    minZ: 0,
    maxZ: 0
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadingProgress, setLoadingProgress] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [cameraPoses, setCameraPoses] = useState<CameraPose[]>([]);
  const [selectedCamera, setSelectedCamera] = useState<CameraPose | null>(null);

  // Measurement state
  const [measurePoints, setMeasurePoints] = useState<THREE.Vector3[]>([]);
  const [measureDistance, setMeasureDistance] = useState<number | null>(null);   // RAW scene-unit distance (scale applied at display time)
  const [userScale, setUserScale] = useState<number | null>(() => {
    try { const v = localStorage.getItem(`birdseye_scale_${projectId}`); return v ? Number(v) : null; } catch { return null; }
  });
  const [knownLength, setKnownLength] = useState<string>('');

  // Three.js instances refs
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const dirLightRef = useRef<THREE.DirectionalLight | null>(null);

  // Objects refs
  const currentObjectRef = useRef<THREE.Object3D | null>(null);
  const baseGeometryRef = useRef<THREE.BufferGeometry | null>(null);
  const originalColorsRef = useRef<Float32Array | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);
  const axesHelperRef = useRef<THREE.AxesHelper | null>(null);
  const boxHelperRef = useRef<THREE.BoxHelper | null>(null);
  const camerasGroupRef = useRef<THREE.Group | null>(null);
  const measureGroupRef = useRef<THREE.Group | null>(null);
  const modelRootGroupRef = useRef<THREE.Group | null>(null);
  const centerOffsetRef = useRef<THREE.Vector3>(new THREE.Vector3(0, 0, 0));
  const framingDimRef = useRef<number>(50);
  const robustElevRangeRef = useRef<{ minY: number; maxY: number }>({ minY: -10, maxY: 10 });
  const [invertUp, setInvertUp] = useState<boolean>(false);

  // Presentation / sharing features (turntable, drone fly-through, fullscreen, share link, mini-map)
  const [autoRotate, setAutoRotate] = useState<boolean>(false);
  const [flying, setFlying] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showMiniMap, setShowMiniMap] = useState<boolean>(false);
  const [toast, setToast] = useState<string | null>(null);
  const [coverageDismissed, setCoverageDismissed] = useState<boolean>(false);
  const miniMapRef = useRef<HTMLCanvasElement | null>(null);
  const rootDivRef = useRef<HTMLDivElement | null>(null);
  const viewRestoredRef = useRef<boolean>(false);

  // Available candidate files
  const meshFile = files['model_mesh.ply'] || files['model.obj'];
  const denseCloudFile = files['dense_cloud_fused_ai.ply'] || files['dense_cloud_filtered.ply'] || files['dense_cloud.ply'] || files['dense_cloud_ai.ply'];
  const sparseCloudFile = files['sparse_cloud.ply'];
  const pointFile = denseCloudFile || sparseCloudFile;
  const camerasFile = files['cameras.json'];

  // Calibration check from quality report
  const gpsCalibrated = Boolean(
    qualityReport?.georeferencing?.survey_grade ||
    (qualityReport?.georeferencing?.status && !qualityReport?.georeferencing?.status?.toLowerCase().includes('unknown'))
  );
  // GPS-scaled aerial models: 1 scene unit = metresPerSceneUnit metres; heights were drawn exaggerated by vertExag
  const metresPerSceneUnit: number = Number(qualityReport?.georeferencing?.metres_per_scene_unit) || 1;
  const vertExag: number = Number(qualityReport?.georeferencing?.vertical_exaggeration) || 1;
  const isCalibrated = gpsCalibrated || userScale != null;   // GPS scale, or scale set from a known real length
  const geoScale = gpsCalibrated ? metresPerSceneUnit : (userScale ?? 1);
  const unitSuffix = isCalibrated ? 'm' : ' (rel)';
  const unitElev = isCalibrated ? 'm' : ' rel';

  // Size / elevation readouts are computed here (not at load time) so 'Set scale' and GPS scale apply immediately
  const boundsText = !rawDims ? stats.bounds
    : rawDims.isCloud ? `${rawDims.sx.toFixed(1)} × ${rawDims.sz.toFixed(1)} × ${rawDims.sy.toFixed(1)} (p1-p99)`
      : `${(rawDims.sx * geoScale).toFixed(1)} × ${(rawDims.sz * geoScale).toFixed(1)} × ${(rawDims.sy * geoScale / vertExag).toFixed(1)}${unitSuffix}`;
  const elevText = !rawDims ? stats.elevationSpan
    : rawDims.isCloud ? `${rawDims.elev.toFixed(1)} (p1-p99)`
      : `${(rawDims.elev * geoScale / vertExag).toFixed(1)}${unitElev}`;

  // Intelligently pick target geometry file based on displayMode
  const targetFile = displayMode === 'points' ? (pointFile || meshFile) : (meshFile || pointFile);

  const getSourceLabel = (): string => {
    if (!targetFile) return 'No Model';
    if (targetFile.filename === 'dense_cloud_fused_ai.ply') return 'AI-Enhanced Dense Cloud (MVS + Depth Anything V2)';
    if (targetFile.filename === 'dense_cloud_ai.ply') return 'AI Dense Cloud (Depth Anything V2)';
    if (targetFile.filename === 'dense_cloud_filtered.ply') return 'Dense MVS Point Cloud (SOR Filtered)';
    if (targetFile.filename === 'dense_cloud.ply') return 'Dense MVS Point Cloud (Raw Fused)';
    if (targetFile.filename === 'sparse_cloud.ply') return 'Sparse SfM Point Cloud';
    if (targetFile.filename === 'model_mesh.ply' || targetFile.filename.endsWith('.obj')) {
      const isAtlas = qualityReport?.mesh?.texture_type === 'atlas';
      return isAtlas ? 'Textured 3D Mesh' : 'Vertex-Colored Surface Mesh';
    }
    return targetFile.filename;
  };

  // 1. Initialize Three.js scene, camera, lights, controls
  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x181B20);
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 2000);
    camera.position.set(0, 30, 60);
    cameraRef.current = camera;

    // WebGL Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.screenSpacePanning = true;
    controls.maxDistance = 1500;
    controls.minDistance = 0.5;
    controlsRef.current = controls;

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const hemiLight = new THREE.HemisphereLight(0xddeeff, 0x202020, 0.4);
    scene.add(hemiLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    scene.add(dirLight);
    dirLightRef.current = dirLight;

    // Scene Helpers
    const grid = new THREE.GridHelper(100, 50, 0x2f7018, 0x3a4049);
    grid.position.y = -0.05;
    scene.add(grid);
    gridHelperRef.current = grid;

    const axes = new THREE.AxesHelper(5);
    scene.add(axes);
    axesHelperRef.current = axes;

    // Master container for reconstructed model and camera flight path
    const rootGroup = new THREE.Group();
    scene.add(rootGroup);
    modelRootGroupRef.current = rootGroup;

    // Camera poses group
    const camGroup = new THREE.Group();
    rootGroup.add(camGroup);
    camerasGroupRef.current = camGroup;

    // Measurement group
    const mGroup = new THREE.Group();
    rootGroup.add(mGroup);
    measureGroupRef.current = mGroup;

    // Render loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Window Resize
    const handleResize = () => {
      if (!containerRef.current || !rendererRef.current || !cameraRef.current) return;
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', handleResize);
      controls.dispose();
      renderer.dispose();
    };
  }, []);

  // 2. Fetch Drone Cameras JSON
  useEffect(() => {
    if (!camerasFile) {
      setCameraPoses([]);
      return;
    }
    fetch(`/api/projects/${projectId}/files/cameras.json`)
      .then((res) => (res.ok ? res.json() : []))
      .then((poses: CameraPose[]) => setCameraPoses(poses))
      .catch((err) => console.warn('Could not fetch cameras.json:', err));
  }, [projectId, camerasFile]);

  // 3. Update Sunlight Direction
  useEffect(() => {
    if (!dirLightRef.current) return;
    const phi = THREE.MathUtils.degToRad(90 - sunElevation);
    const theta = THREE.MathUtils.degToRad(sunAzimuth);
    const radius = 80;
    const x = radius * Math.sin(phi) * Math.sin(theta);
    const y = radius * Math.cos(phi);
    const z = radius * Math.sin(phi) * Math.cos(theta);
    dirLightRef.current.position.set(x, Math.max(10, y), z);
  }, [sunAzimuth, sunElevation]);

  // 4. Load & Construct 3D Geometry
  const removeCurrentObject = () => {
    const prev = currentObjectRef.current;
    if (!prev) return;
    prev.parent?.remove(prev);
    const mat = (prev as THREE.Mesh | THREE.Points).material;
    if (mat) {
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else mat.dispose();
    }
    currentObjectRef.current = null;
  };

  useEffect(() => {
    if (!targetFile || !sceneRef.current) {
      removeCurrentObject();
      baseGeometryRef.current = null;
      originalColorsRef.current = null;
      setStats({ points: 0, faces: 0, bounds: '--', elevationSpan: '--', minZ: 0, maxZ: 0 });
      return;
    }

    setIsLoading(true);
    setLoadingProgress(`Loading ${targetFile.filename}...`);
    setErrorMsg(null);
    let cancelled = false;   // a newer selection (e.g. Mesh -> Dense -> Mesh) must not be overwritten by a slower, older download

    const loadModel = async () => {
      try {
        const url = `/api/projects/${projectId}/files/${targetFile.filename}`;
        const res = await fetch(url);
        if (cancelled) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to download ${targetFile.filename}`);

        // Clean previous object
        removeCurrentObject();
        if (boxHelperRef.current && sceneRef.current) {
          sceneRef.current.remove(boxHelperRef.current);
          boxHelperRef.current = null;
        }

        let geometry: THREE.BufferGeometry;

        if (targetFile.filename.endsWith('.ply')) {
          setLoadingProgress('Parsing photogrammetric PLY geometry...');
          const buffer = await res.arrayBuffer();
          if (cancelled) return;
          const loader = new PLYLoader();
          geometry = loader.parse(buffer);
        } else if (targetFile.filename.endsWith('.obj')) {
          setLoadingProgress('Parsing OBJ terrain mesh...');
          const text = await res.text();
          if (cancelled) return;
          const loader = new OBJLoader();
          const objGroup = loader.parse(text);

          // Merge or pick first mesh geometry
          let foundGeom: THREE.BufferGeometry | null = null;
          objGroup.traverse((child) => {
            if (!foundGeom && (child as THREE.Mesh).isMesh) {
              foundGeom = (child as THREE.Mesh).geometry;
            }
          });
          if (!foundGeom) throw new Error('No mesh geometry found in OBJ file');
          geometry = foundGeom;
        } else {
          throw new Error(`Unsupported model format: ${targetFile.filename}`);
        }

        // Robust geometry framing and centering
        const isCloud = Boolean(
          targetFile.filename.includes('cloud') ||
          (displayMode === 'points' && (!geometry.index || geometry.index.count === 0))
        );

        geometry.computeBoundingBox();
        const rawBox = geometry.boundingBox || new THREE.Box3();
        const rawSize = rawBox.getSize(new THREE.Vector3());
        const rawCenter = rawBox.getCenter(new THREE.Vector3());

        const posAttr = geometry.attributes.position;
        const ptCount = posAttr ? posAttr.count : 0;

        let center = rawCenter.clone();
        let framingSpan = Math.max(rawSize.x, rawSize.y, rawSize.z, 1.0);
        let minY = rawBox.min.y;
        let maxY = rawBox.max.y;
        let sizeDisplay = rawSize.clone();

        if (ptCount > 50) {  // meshes use the same robust framing as clouds so both overlay correctly
          // Robust quantile statistics (protects from distant outliers / stray far-field geometry)
          const sampleLimit = 30000;
          const stride = Math.max(1, Math.floor(ptCount / sampleLimit));
          const sampleCount = Math.floor(ptCount / stride);

          const xs = new Float32Array(sampleCount);
          const ys = new Float32Array(sampleCount);
          const zs = new Float32Array(sampleCount);

          for (let i = 0, j = 0; i < ptCount && j < sampleCount; i += stride, j++) {
            xs[j] = posAttr.getX(i);
            ys[j] = posAttr.getY(i);
            zs[j] = posAttr.getZ(i);
          }

          xs.sort();
          ys.sort();
          zs.sort();

          const getPct = (arr: Float32Array, p: number) => {
            const idx = Math.min(arr.length - 1, Math.max(0, Math.floor((p / 100) * arr.length)));
            return arr[idx];
          };

          const medX = getPct(xs, 50);
          const medY = getPct(ys, 50);
          const medZ = getPct(zs, 50);

          const p1X = getPct(xs, 1);
          const p99X = getPct(xs, 99);
          const spanX = Math.max(1.0, p99X - p1X);

          const p1Y = getPct(ys, 1);
          const p99Y = getPct(ys, 99);
          const spanY = Math.max(1.0, p99Y - p1Y);

          const p1Z = getPct(zs, 1);
          const p99Z = getPct(zs, 99);
          const spanZ = Math.max(1.0, p99Z - p1Z);

          center = new THREE.Vector3(medX, medY, medZ);
          framingSpan = Math.max(spanX, spanY, spanZ);
          sizeDisplay = new THREE.Vector3(spanX, spanY, spanZ);
          minY = p1Y;
          maxY = p99Y;
        }

        // Store display offsets without modifying raw geometry buffer attributes
        centerOffsetRef.current = center.clone();
        framingDimRef.current = framingSpan;
        robustElevRangeRef.current = { minY, maxY };

        // Cache base geometry and original RGB colors
        baseGeometryRef.current = geometry;
        loadedFileRef.current = targetFile.filename;
        if (geometry.attributes.color) {
          originalColorsRef.current = (geometry.attributes.color.array as Float32Array).slice();
        } else {
          // Generate default colors if not present
          const count = ptCount;
          const defaultCols = new Float32Array(count * 3);
          for (let i = 0; i < count; i++) {
            defaultCols[i * 3] = 0.65;
            defaultCols[i * 3 + 1] = 0.72;
            defaultCols[i * 3 + 2] = 0.65;
          }
          originalColorsRef.current = defaultCols;
          geometry.setAttribute('color', new THREE.BufferAttribute(defaultCols, 3));
        }

        const pointCount = ptCount;
        const faceCount = geometry.index ? geometry.index.count / 3 : 0;

        const boundsString = isCloud
          ? `${sizeDisplay.x.toFixed(1)} × ${sizeDisplay.z.toFixed(1)} × ${sizeDisplay.y.toFixed(1)} (p1-p99)`
          : `${(sizeDisplay.x * geoScale).toFixed(1)} × ${(sizeDisplay.z * geoScale).toFixed(1)} × ${(sizeDisplay.y * geoScale / vertExag).toFixed(1)}${unitSuffix}`;

        const elevSpanString = isCloud
          ? `${(maxY - minY).toFixed(1)} (p1-p99)`
          : `${((maxY - minY) * geoScale / vertExag).toFixed(1)}${unitElev}`;

        setRawDims({ isCloud, sx: sizeDisplay.x, sz: sizeDisplay.z, sy: sizeDisplay.y, elev: maxY - minY });
        setStats({
          points: pointCount,
          faces: Math.round(faceCount),
          bounds: boundsString,
          elevationSpan: elevSpanString,
          minZ: minY,
          maxZ: maxY
        });

        // Create Object (Points or Mesh)
        rebuildObject(geometry, displayMode, colorMode, pointSize, sizeAttenuation);

        // Adjust Grid position to sit right under lowest terrain point
        if (gridHelperRef.current) {
          gridHelperRef.current.position.set(0, (minY - center.y) - 0.2, 0);
        }

        // Fit Camera with robust clipping planes and distance
        const maxDim = framingSpan;
        if (cameraRef.current && controlsRef.current) {
          cameraRef.current.near = Math.max(0.1, maxDim * 0.005);
          cameraRef.current.far = Math.max(3000, maxDim * 30);
          cameraRef.current.updateProjectionMatrix();

          cameraRef.current.position.set(maxDim * 0.9, maxDim * 0.8, maxDim * 1.2);
          controlsRef.current.target.set(0, 0, 0);
          controlsRef.current.update();
        }

        setIsLoading(false);
      } catch (err: any) {
        if (cancelled) return;
        console.error('Failed to load 3D terrain:', err);
        setErrorMsg(err.message || 'Error processing 3D model geometry');
        setIsLoading(false);
      }
    };

    loadModel();
    return () => { cancelled = true; };
  }, [targetFile?.filename, projectId]);

  // 5. Rebuild Object Materials / Colors upon mode changes
  const rebuildObject = (
    geom: THREE.BufferGeometry,
    dMode: DisplayMode,
    cMode: ColorMode,
    pSize: number,
    sAtten: boolean
  ) => {
    if (!sceneRef.current) return;

    removeCurrentObject();

    // Apply color scheme to geometry
    applyColorScheme(geom, cMode);

    let obj: THREE.Object3D;
    const isPointCloud = dMode === 'points' || !geom.index;

    if (isPointCloud) {
      const pMat = new THREE.PointsMaterial({
        size: pSize * (sAtten ? 0.08 : 1.0),
        sizeAttenuation: sAtten,
        vertexColors: true
      });
      obj = new THREE.Points(geom, pMat);
    } else {
      geom.computeVertexNormals();
      const mMat = new THREE.MeshStandardMaterial({
        vertexColors: cMode !== 'normals',
        roughness: 0.75,
        metalness: 0.1,
        wireframe: dMode === 'wireframe',
        flatShading: false,
        side: THREE.DoubleSide
      });
      obj = new THREE.Mesh(geom, mMat);
      obj.castShadow = true;
      obj.receiveShadow = true;
    }

    // Apply display translation to center model without mutating raw geometry buffer
    const offset = centerOffsetRef.current || new THREE.Vector3(0, 0, 0);
    obj.position.set(-offset.x, -offset.y, -offset.z);

    if (modelRootGroupRef.current) {
      modelRootGroupRef.current.add(obj);
    } else if (sceneRef.current) {
      sceneRef.current.add(obj);
    }
    currentObjectRef.current = obj;

    // Update Bounding Box Helper
    if (boxHelperRef.current) {
      sceneRef.current.remove(boxHelperRef.current);
    }
    const bHelper = new THREE.BoxHelper(obj, 0xa7ed79);
    bHelper.visible = showBox;
    sceneRef.current.add(bHelper);
    boxHelperRef.current = bHelper;
  };

  // 6. Colormap Application Function (RGB vs Elevation vs Normals)
  const applyColorScheme = (geom: THREE.BufferGeometry, cMode: ColorMode) => {
    const posAttr = geom.attributes.position;
    if (!posAttr) return;
    const count = posAttr.count;

    let colorsArr = (geom.attributes.color?.array as Float32Array) || new Float32Array(count * 3);

    if (cMode === 'rgb') {
      if (originalColorsRef.current) {
        colorsArr.set(originalColorsRef.current);
      }
    } else if (cMode === 'elevation') {
      // Find min and max height using robust elevation statistics
      const minY = robustElevRangeRef.current.minY;
      const maxY = robustElevRangeRef.current.maxY;
      const effMin = invertUp ? -maxY : minY;
      const effMax = invertUp ? -minY : maxY;
      const range = Math.max(0.001, effMax - effMin);

      for (let i = 0; i < count; i++) {
        const rawY = posAttr.getY(i);
        const y = invertUp ? -rawY : rawY;
        const normH = THREE.MathUtils.clamp((y - effMin) / range, 0, 1);
        const c = getElevationColor(normH);
        colorsArr[i * 3] = c.r;
        colorsArr[i * 3 + 1] = c.g;
        colorsArr[i * 3 + 2] = c.b;
      }
    } else if (cMode === 'normals') {
      geom.computeVertexNormals();
      const normAttr = geom.attributes.normal;
      if (normAttr) {
        for (let i = 0; i < count; i++) {
          const nx = normAttr.getX(i);
          const ny = normAttr.getY(i);
          const nz = normAttr.getZ(i);
          colorsArr[i * 3] = nx * 0.5 + 0.5;
          colorsArr[i * 3 + 1] = ny * 0.5 + 0.5;
          colorsArr[i * 3 + 2] = nz * 0.5 + 0.5;
        }
      }
    }

    geom.setAttribute('color', new THREE.BufferAttribute(colorsArr, 3));
    geom.attributes.color.needsUpdate = true;
  };

  // Hypsometric elevation tint palette: Blue -> Cyan -> Emerald Green -> Warm Yellow -> Orange -> Crimson
  const getElevationColor = (t: number): THREE.Color => {
    if (t < 0.2) {
      // Deep Navy to Cyan
      const factor = t / 0.2;
      return new THREE.Color().lerpColors(new THREE.Color(0x1a3680), new THREE.Color(0x17a2b8), factor);
    } else if (t < 0.45) {
      // Cyan to Emerald Green
      const factor = (t - 0.2) / 0.25;
      return new THREE.Color().lerpColors(new THREE.Color(0x17a2b8), new THREE.Color(0x28a745), factor);
    } else if (t < 0.7) {
      // Emerald Green to Golden Yellow
      const factor = (t - 0.45) / 0.25;
      return new THREE.Color().lerpColors(new THREE.Color(0x28a745), new THREE.Color(0xffc107), factor);
    } else if (t < 0.88) {
      // Yellow to Vibrant Orange
      const factor = (t - 0.7) / 0.18;
      return new THREE.Color().lerpColors(new THREE.Color(0xffc107), new THREE.Color(0xfd7e14), factor);
    } else {
      // Orange to Crimson Red
      const factor = (t - 0.88) / 0.12;
      return new THREE.Color().lerpColors(new THREE.Color(0xfd7e14), new THREE.Color(0xd92534), factor);
    }
  };

  // 7. Update display/color modes dynamically
  useEffect(() => {
    // only restyle geometry that belongs to the currently selected file (not a stale one still on screen)
    if (baseGeometryRef.current && loadedFileRef.current === targetFile?.filename) {
      rebuildObject(baseGeometryRef.current, displayMode, colorMode, pointSize, sizeAttenuation);
    }
  }, [displayMode, colorMode, pointSize, sizeAttenuation]);

  // 8. Render Drone Cameras & Flight Path
  useEffect(() => {
    if (!camerasGroupRef.current) return;
    const group = camerasGroupRef.current;
    group.clear();

    if (!showCameras || cameraPoses.length === 0 || !baseGeometryRef.current) {
      group.visible = false;
      return;
    }
    group.visible = true;
    const offset = centerOffsetRef.current || new THREE.Vector3(0, 0, 0);

    // Flight Path Line
    const pathPoints: THREE.Vector3[] = [];
    cameraPoses.forEach((cam) => {
      pathPoints.push(new THREE.Vector3(
        cam.position[0] - offset.x,
        cam.position[1] - offset.y,
        cam.position[2] - offset.z
      ));
    });

    const pathGeom = new THREE.BufferGeometry().setFromPoints(pathPoints);
    const pathMat = new THREE.LineBasicMaterial({
      color: 0xa7ed79,
      linewidth: 2,
      transparent: true,
      opacity: 0.85
    });
    const pathLine = new THREE.Line(pathGeom, pathMat);
    group.add(pathLine);

    // Camera Frustum Pyramids
    const coneGeom = new THREE.ConeGeometry(0.6, 1.2, 4);
    coneGeom.rotateX(-Math.PI / 2);
    const coneMat = new THREE.MeshBasicMaterial({
      color: 0x4dd0e1,
      wireframe: true
    });

    cameraPoses.forEach((cam) => {
      const cone = new THREE.Mesh(coneGeom, coneMat);
      cone.position.set(
        cam.position[0] - offset.x,
        cam.position[1] - offset.y,
        cam.position[2] - offset.z
      );

      // Direct viewing direction
      const targetPos = new THREE.Vector3(
        cam.position[0] - offset.x + cam.direction[0],
        cam.position[1] - offset.y + cam.direction[1],
        cam.position[2] - offset.z + cam.direction[2]
      );
      cone.lookAt(targetPos);
      cone.userData = { cameraPose: cam };
      group.add(cone);
    });
  }, [showCameras, cameraPoses]);

  // 9. Update Scene Helpers Visibility
  useEffect(() => {
    if (gridHelperRef.current) gridHelperRef.current.visible = showGrid;
    if (axesHelperRef.current) axesHelperRef.current.visible = showAxes;
    if (boxHelperRef.current) boxHelperRef.current.visible = showBox;
  }, [showGrid, showAxes, showBox]);

  // 10. Camera Presets
  const setCameraView = (view: 'top' | 'iso' | 'front' | 'side' | 'reset') => {
    if (!cameraRef.current || !controlsRef.current || !baseGeometryRef.current) return;
    const geom = baseGeometryRef.current;
    geom.computeBoundingBox();
    const size = geom.boundingBox!.getSize(new THREE.Vector3());
    const fallbackDim = Math.max(size.x, size.y, size.z);
    const maxDim = (framingDimRef.current && framingDimRef.current > 0) ? framingDimRef.current : (fallbackDim > 0 ? fallbackDim : 50);

    controlsRef.current.target.set(0, 0, 0);

    if (view === 'top') {
      cameraRef.current.position.set(0, maxDim * 2.2, 0.001);
    } else if (view === 'iso') {
      cameraRef.current.position.set(maxDim * 1.1, maxDim * 0.9, maxDim * 1.1);
    } else if (view === 'front') {
      cameraRef.current.position.set(0, maxDim * 0.2, maxDim * 1.6);
    } else if (view === 'side') {
      cameraRef.current.position.set(maxDim * 1.6, maxDim * 0.2, 0);
    } else if (view === 'reset') {
      cameraRef.current.position.set(maxDim * 0.9, maxDim * 0.8, maxDim * 1.2);
    }
    controlsRef.current.update();
  };

  // 11. Flip Up/Down Orientation Toggle
  const handleToggleFlip = () => {
    const nextInvert = !invertUp;
    setInvertUp(nextInvert);
    if (modelRootGroupRef.current) {
      modelRootGroupRef.current.rotation.x = nextInvert ? Math.PI : 0;
    }
    if (baseGeometryRef.current && colorMode === 'elevation') {
      applyColorScheme(baseGeometryRef.current, 'elevation');
    }
  };

  // 11. Interactive Distance Measurement Tool via Raycasting
  const handleCanvasClick = (e: React.MouseEvent) => {
    if (!measureMode || !containerRef.current || !cameraRef.current || !currentObjectRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, cameraRef.current);
    const intersects = raycaster.intersectObject(currentObjectRef.current, true);

    if (intersects.length > 0) {
      const hitPoint = intersects[0].point;
      const newPts = [...measurePoints, hitPoint];
      if (newPts.length > 2) {
        setMeasurePoints([hitPoint]);
        setMeasureDistance(null);
        renderMeasurement([hitPoint]);
      } else {
        setMeasurePoints(newPts);
        if (newPts.length === 2) {
          const dv = newPts[1].clone().sub(newPts[0]);
          dv.y = dv.y / vertExag;                              // undo the display-only vertical exaggeration
          setMeasureDistance(dv.length());
          renderMeasurement(newPts);
        } else {
          renderMeasurement(newPts);
        }
      }
    }
  };

  const renderMeasurement = (pts: THREE.Vector3[]) => {
    if (!measureGroupRef.current) return;
    const group = measureGroupRef.current;
    group.clear();

    pts.forEach((p, idx) => {
      const sphere = new THREE.Mesh(
        new THREE.SphereGeometry(Math.max(framingDimRef.current * 0.008, 0.001), 16, 16),
        new THREE.MeshBasicMaterial({ color: idx === 0 ? 0xff4081 : 0x00e676 })
      );
      sphere.position.copy(p);
      group.add(sphere);
    });

    if (pts.length === 2) {
      const lineGeom = new THREE.BufferGeometry().setFromPoints(pts);
      const lineMat = new THREE.LineBasicMaterial({ color: 0xffff00, linewidth: 3 });
      const line = new THREE.Line(lineGeom, lineMat);
      group.add(line);
    }
  };

  const clearMeasurement = () => {
    setMeasurePoints([]);
    setMeasureDistance(null);
    measureGroupRef.current?.clear();
  };

  // 12. Snapshot PNG Export
  const takeSnapshot = () => {
    if (!rendererRef.current) return;
    const dataUrl = rendererRef.current.domElement.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = `birds_eye_terrain_${projectId}.png`;
    a.click();
  };

  // ---- Presentation features ------------------------------------------------------------
  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 2200);
  };

  // Turntable: slow orbit around the model (stops as soon as the user grabs the view).
  useEffect(() => {
    const c = controlsRef.current;
    if (!c) return;
    c.autoRotate = autoRotate && !flying;
    c.autoRotateSpeed = 1.6;
    if (!autoRotate) return;
    const stop = () => setAutoRotate(false);
    const el = c.domElement;
    el.addEventListener('pointerdown', stop);
    return () => el.removeEventListener('pointerdown', stop);
  }, [autoRotate, flying]);

  // Fly-through: replay the drone's flight path as a camera move (the real-time-video counterpart of a tour).
  useEffect(() => {
    if (!flying) return;
    const root = modelRootGroupRef.current;
    const cam = cameraRef.current;
    const controls = controlsRef.current;
    if (!root || !cam || !controls || cameraPoses.length < 2) { setFlying(false); return; }
    root.updateMatrixWorld(true);
    const offset = centerOffsetRef.current;
    const quat = root.getWorldQuaternion(new THREE.Quaternion());
    const positions = cameraPoses.map(p => root.localToWorld(new THREE.Vector3(
      p.position[0] - offset.x, p.position[1] - offset.y, p.position[2] - offset.z)));
    const dirs = cameraPoses.map(p => new THREE.Vector3(p.direction[0], p.direction[1], p.direction[2]).normalize().applyQuaternion(quat));
    const curve = new THREE.CatmullRomCurve3(positions, false, 'centripetal');
    const saved = { pos: cam.position.clone(), target: controls.target.clone(), near: cam.near };
    const durationMs = Math.min(40000, Math.max(8000, cameraPoses.length * 700));
    controls.enabled = false;
    controls.autoRotate = false;
    cam.near = Math.max(0.05, framingDimRef.current * 0.001);
    cam.updateProjectionMatrix();
    const t0 = performance.now();
    let raf = 0;
    const step = () => {
      const t = Math.min(1, (performance.now() - t0) / durationMs);
      const pos = curve.getPoint(t);
      const f = t * (positions.length - 1);
      const i = Math.min(positions.length - 2, Math.floor(f));
      const dir = dirs[i].clone().lerp(dirs[i + 1], f - i).normalize();
      cam.position.copy(pos);
      cam.lookAt(pos.clone().add(dir));
      if (t < 1) raf = requestAnimationFrame(step); else setFlying(false);
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      cam.near = saved.near;
      cam.updateProjectionMatrix();
      cam.position.copy(saved.pos);
      controls.target.copy(saved.target);
      controls.enabled = true;
      controls.update();
    };
  }, [flying, cameraPoses]);

  // Fullscreen
  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === rootDivRef.current);
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);
  const toggleFullscreen = () => {
    const el = rootDivRef.current;
    if (!el) return;
    if (document.fullscreenElement) { void document.exitFullscreen(); return; }
    el.requestFullscreen?.().catch(() => showToast('Fullscreen is not available in this browser.'));
  };

  // Share: the link carries the camera position, so opening it shows exactly this view.
  const viewHash = () => {
    const c = cameraRef.current, t = controlsRef.current?.target;
    if (!c || !t) return '';
    const r = (n: number) => Math.round(n * 1000) / 1000;
    return `#view=${[c.position.x, c.position.y, c.position.z, t.x, t.y, t.z].map(r).join(',')},${invertUp ? 1 : 0}`;
  };
  const copyViewLink = async () => {
    const url = `${window.location.origin}${window.location.pathname}${window.location.search}${viewHash()}`;
    try {
      await navigator.clipboard.writeText(url);
      showToast('View link copied');
    } catch {
      window.prompt('Copy this link:', url);
    }
  };
  // Restore a shared view once the model has loaded.
  useEffect(() => {
    if (viewRestoredRef.current || isLoading || !stats) return;
    const m = /view=([-0-9.,]+)/.exec(window.location.hash);
    viewRestoredRef.current = true;
    if (!m || !cameraRef.current || !controlsRef.current) return;
    const v = m[1].split(',').map(Number);
    if (v.length < 7 || v.some(n => !Number.isFinite(n))) return;
    if (v[6] === 1) { setInvertUp(true); if (modelRootGroupRef.current) modelRootGroupRef.current.rotation.x = Math.PI; }
    cameraRef.current.position.set(v[0], v[1], v[2]);
    controlsRef.current.target.set(v[3], v[4], v[5]);
    controlsRef.current.update();
  }, [isLoading, stats]);

  // Mini-map: top-down plan of the model with the drone path and the current viewpoint.
  useEffect(() => {
    if (!showMiniMap) return;
    const canvas = miniMapRef.current, geom = baseGeometryRef.current, root = modelRootGroupRef.current;
    if (!canvas || !geom || !root) return;
    const pos = geom.getAttribute('position'), col = geom.getAttribute('color');
    if (!pos) return;
    root.updateMatrixWorld(true);
    const n = pos.count, stride = Math.max(1, Math.floor(n / 6000));
    const pts: { x: number; z: number; c: string }[] = [];
    const v = new THREE.Vector3();
    for (let i = 0; i < n; i += stride) {
      v.fromBufferAttribute(pos, i); root.localToWorld(v);
      const c = col ? `rgb(${Math.round(col.getX(i) * 255)},${Math.round(col.getY(i) * 255)},${Math.round(col.getZ(i) * 255)})` : '#9aa';
      pts.push({ x: v.x, z: v.z, c });
    }
    const offset = centerOffsetRef.current;
    const path = cameraPoses.map(p => { const w = root.localToWorld(new THREE.Vector3(p.position[0] - offset.x, p.position[1] - offset.y, p.position[2] - offset.z)); return { x: w.x, z: w.z }; });
    const all = [...pts, ...path];
    const xs = all.map(p => p.x).sort((a, b) => a - b), zs = all.map(p => p.z).sort((a, b) => a - b);
    const q = (a: number[], f: number) => a[Math.min(a.length - 1, Math.max(0, Math.floor(f * (a.length - 1))))];
    const x0 = q(xs, 0.01), x1 = q(xs, 0.99), z0 = q(zs, 0.01), z1 = q(zs, 0.99);
    const W = canvas.width, H = canvas.height, pad = 10;
    const sc = Math.min((W - 2 * pad) / Math.max(1e-6, x1 - x0), (H - 2 * pad) / Math.max(1e-6, z1 - z0));
    const px = (x: number) => W / 2 + (x - (x0 + x1) / 2) * sc, pz = (z: number) => H / 2 + (z - (z0 + z1) / 2) * sc;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = 'rgba(20,23,28,0.92)'; ctx.fillRect(0, 0, W, H);
      for (const p of pts) { ctx.fillStyle = p.c; ctx.fillRect(px(p.x), pz(p.z), 2, 2); }
      if (path.length > 1) {
        ctx.strokeStyle = '#a7ed79'; ctx.lineWidth = 1.5; ctx.beginPath();
        path.forEach((p, i) => (i ? ctx.lineTo(px(p.x), pz(p.z)) : ctx.moveTo(px(p.x), pz(p.z)))); ctx.stroke();
      }
      const c = cameraRef.current;
      if (c) {
        const d = new THREE.Vector3(); c.getWorldDirection(d);
        const cx = px(c.position.x), cz = pz(c.position.z), a = Math.atan2(d.z, d.x);
        ctx.fillStyle = 'rgba(255,214,10,0.35)'; ctx.beginPath(); ctx.moveTo(cx, cz);
        ctx.arc(cx, cz, 26, a - 0.5, a + 0.5); ctx.closePath(); ctx.fill();
        ctx.fillStyle = '#ffd60a'; ctx.beginPath(); ctx.arc(cx, cz, 3.5, 0, Math.PI * 2); ctx.fill();
      }
    };
    draw();
    const id = window.setInterval(draw, 120);
    return () => window.clearInterval(id);
  }, [showMiniMap, isLoading, invertUp, cameraPoses, displayMode, colorMode]);

  return (
    <div ref={rootDivRef} style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden', userSelect: 'none', backgroundColor: '#14171c' }}>

      {/* 3D WebGL Canvas */}
      <div
        ref={containerRef}
        onClick={handleCanvasClick}
        style={{
          width: '100%',
          height: '100%',
          cursor: measureMode ? 'crosshair' : 'grab'
        }}
      />

      {/* Top bars share one wrapping row so they never overlap on narrow windows */}
      <div style={{ position: 'absolute', top: '12px', left: '12px', right: '12px', display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', zIndex: 10, pointerEvents: 'none' }}>
        {/* Main Top Control Toolbar */}
        <div
          style={{
            position: 'relative',
            pointerEvents: 'auto',
            maxWidth: '100%',
            flexWrap: 'wrap',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            backgroundColor: 'rgba(23, 26, 32, 0.92)',
            backdropFilter: 'blur(8px)',
            padding: '6px 8px',
            borderRadius: '6px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.35)',
            zIndex: 10
          }}
        >
          {/* Render Display Mode */}
          <div style={{ display: 'flex', gap: '2px', backgroundColor: 'rgba(255, 255, 255, 0.06)', borderRadius: '4px', padding: '2px' }}>
            <button
              onClick={() => setDisplayMode('points')}
              style={{
                padding: '4px 8px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '3px',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: displayMode === 'points' ? 'var(--accent-lime)' : 'transparent',
                color: displayMode === 'points' ? '#171A20' : '#BAC0CB'
              }}
            >
              {denseCloudFile ? 'Dense Cloud (MVS)' : 'Sparse SfM Cloud'}
            </button>
            <button
              onClick={() => setDisplayMode('solid')}
              style={{
                padding: '4px 8px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '3px',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: displayMode === 'solid' ? 'var(--accent-lime)' : 'transparent',
                color: displayMode === 'solid' ? '#171A20' : '#BAC0CB'
              }}
            >
              Surface Mesh
            </button>
            <button
              onClick={() => setDisplayMode('wireframe')}
              style={{
                padding: '4px 8px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '3px',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: displayMode === 'wireframe' ? 'var(--accent-lime)' : 'transparent',
                color: displayMode === 'wireframe' ? '#171A20' : '#BAC0CB'
              }}
            >
              Wireframe
            </button>
          </div>

          <div style={{ width: '1px', height: '16px', backgroundColor: 'rgba(255, 255, 255, 0.15)', margin: '0 2px' }} />

          {/* Color Palette Switcher */}
          <div style={{ display: 'flex', gap: '2px', backgroundColor: 'rgba(255, 255, 255, 0.06)', borderRadius: '4px', padding: '2px' }}>
            <button
              onClick={() => setColorMode('rgb')}
              title="Real Drone Aerial Colors"
              style={{
                padding: '4px 8px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '3px',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: colorMode === 'rgb' ? '#2F7018' : 'transparent',
                color: colorMode === 'rgb' ? '#FFFFFF' : '#BAC0CB',
                display: 'flex',
                alignItems: 'center',
                gap: '4px'
              }}
            >
              <Palette size={12} /> RGB Photo
            </button>
            <button
              onClick={() => setColorMode('elevation')}
              title="Elevation Heatmap / Hypsometric Tint"
              style={{
                padding: '4px 8px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '3px',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: colorMode === 'elevation' ? '#2F7018' : 'transparent',
                color: colorMode === 'elevation' ? '#FFFFFF' : '#BAC0CB',
                display: 'flex',
                alignItems: 'center',
                gap: '4px'
              }}
            >
              <Layers size={12} /> Elevation
            </button>
            <button
              onClick={() => setColorMode('normals')}
              title="Surface Normals & Slope Relief"
              style={{
                padding: '4px 8px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '3px',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: colorMode === 'normals' ? '#2F7018' : 'transparent',
                color: colorMode === 'normals' ? '#FFFFFF' : '#BAC0CB',
                display: 'flex',
                alignItems: 'center',
                gap: '4px'
              }}
            >
              <Eye size={12} /> Normals
            </button>
          </div>

          <div style={{ width: '1px', height: '16px', backgroundColor: 'rgba(255, 255, 255, 0.15)', margin: '0 2px' }} />

          {/* Drone Flight Path & Camera Stations Toggle */}
          <button
            onClick={() => setShowCameras(!showCameras)}
            title="Toggle Drone Flight Trajectory & Camera Frustums"
            style={{
              background: showCameras ? 'rgba(167, 237, 121, 0.18)' : 'transparent',
              border: showCameras ? '1px solid var(--accent-lime)' : '1px solid transparent',
              borderRadius: '4px',
              cursor: 'pointer',
              color: showCameras ? 'var(--accent-lime)' : '#BAC0CB',
              padding: '4px 8px',
              fontSize: '11px',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
          >
            <Camera size={13} />
            <span>Flight Path ({cameraPoses.length})</span>
          </button>

          {/* 3D Distance Measurement Tool */}
          <button
            onClick={() => {
              setMeasureMode(!measureMode);
              if (measureMode) clearMeasurement();
            }}
            title="Measure 3D Distance between 2 points"
            style={{
              background: measureMode ? 'rgba(255, 235, 59, 0.2)' : 'transparent',
              border: measureMode ? '1px solid #ffeb3b' : '1px solid transparent',
              borderRadius: '4px',
              cursor: 'pointer',
              color: measureMode ? '#ffeb3b' : '#BAC0CB',
              padding: '4px 8px',
              fontSize: '11px',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
          >
            <Ruler size={13} />
            <span>Measure</span>
          </button>

          {/* Sunlight Controls Toggle */}
          <button
            onClick={() => setShowLightingControls(!showLightingControls)}
            title="Adjust Sun Azimuth & Elevation Shadows"
            style={{
              background: showLightingControls ? 'rgba(255, 193, 7, 0.2)' : 'transparent',
              border: showLightingControls ? '1px solid #ffc107' : '1px solid transparent',
              borderRadius: '4px',
              cursor: 'pointer',
              color: showLightingControls ? '#ffc107' : '#BAC0CB',
              padding: '4px 6px'
            }}
          >
            <Sun size={14} />
          </button>

          {/* Scene Helpers */}
          <button
            onClick={() => setShowGrid(!showGrid)}
            title="Toggle Ground Grid"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: showGrid ? 'var(--accent-lime)' : '#7E8694',
              padding: '4px 6px'
            }}
          >
            <Grid size={15} />
          </button>

          <button
            onClick={() => setShowBox(!showBox)}
            title="Toggle Bounding Extents Box"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: showBox ? 'var(--accent-lime)' : '#7E8694',
              padding: '4px 6px'
            }}
          >
            <Box size={15} />
          </button>

          <button
            onClick={() => setShowAxes(!showAxes)}
            title="Toggle 3D Coordinate Compass"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: showAxes ? 'var(--accent-lime)' : '#7E8694',
              padding: '4px 6px'
            }}
          >
            <Compass size={15} />
          </button>

          {/* Snapshot PNG */}
          <button
            onClick={takeSnapshot}
            title="Export High-Resolution PNG Snapshot"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: '#BAC0CB',
              padding: '4px 6px'
            }}
          >
            <Download size={15} />
          </button>
        </div>

        {/* Camera View Presets Floating Bar (Top Right) */}
        <div
          style={{
            position: 'relative',
            pointerEvents: 'auto',
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            backgroundColor: 'rgba(23, 26, 32, 0.92)',
            backdropFilter: 'blur(8px)',
            padding: '4px 6px',
            borderRadius: '6px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.35)',
            zIndex: 10
          }}
        >
          <span style={{ fontSize: '10px', fontWeight: 700, color: '#7E8694', padding: '0 4px' }}>VIEW</span>
          <button
            onClick={() => setCameraView('top')}
            title="Nadir / Top-Down Map View"
            style={{
              padding: '4px 6px',
              fontSize: '11px',
              fontWeight: 600,
              borderRadius: '3px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              backgroundColor: '#242931',
              color: '#BAC0CB',
              cursor: 'pointer'
            }}
          >
            Top (Nadir)
          </button>
          <button
            onClick={() => setCameraView('iso')}
            title="45° Perspective Isometric"
            style={{
              padding: '4px 6px',
              fontSize: '11px',
              fontWeight: 600,
              borderRadius: '3px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              backgroundColor: '#242931',
              color: '#BAC0CB',
              cursor: 'pointer'
            }}
          >
            Isometric
          </button>
          <button
            onClick={() => setCameraView('front')}
            title="Front Elevation Profile"
            style={{
              padding: '4px 6px',
              fontSize: '11px',
              fontWeight: 600,
              borderRadius: '3px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              backgroundColor: '#242931',
              color: '#BAC0CB',
              cursor: 'pointer'
            }}
          >
            Front
          </button>
          <button
            onClick={() => setCameraView('side')}
            title="Side Cross-Section Profile"
            style={{
              padding: '4px 6px',
              fontSize: '11px',
              fontWeight: 600,
              borderRadius: '3px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              backgroundColor: '#242931',
              color: '#BAC0CB',
              cursor: 'pointer'
            }}
          >
            Side
          </button>
          <button
            onClick={() => setCameraView('reset')}
            title="Fit & Center Model"
            style={{
              padding: '4px 6px',
              fontSize: '11px',
              fontWeight: 600,
              borderRadius: '3px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              backgroundColor: '#242931',
              color: 'var(--accent-lime)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '2px'
            }}
          >
            <RotateCcw size={11} /> Reset
          </button>
          <div style={{ width: '1px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.15)', margin: '0 2px' }} />
          <button
            onClick={handleToggleFlip}
            title="Invert Vertical Orientation (Flip Model Right-Side Up)"
            style={{
              padding: '4px 7px',
              fontSize: '11px',
              fontWeight: 600,
              borderRadius: '3px',
              border: invertUp ? '1px solid var(--accent-lime)' : '1px solid rgba(255, 255, 255, 0.12)',
              backgroundColor: invertUp ? 'rgba(74, 222, 128, 0.18)' : '#242931',
              color: invertUp ? 'var(--accent-lime)' : '#BAC0CB',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '3px'
            }}
          >
            <span>{invertUp ? 'Upright (Flipped)' : 'Flip Up'}</span>
          </button>
        </div>
      </div>

      {/* Coverage notice: tells the user whether the video went around the subject */}
      {qualityReport?.coverage?.available && qualityReport.coverage.level !== 'good' && !coverageDismissed && (
        <div
          style={{
            position: 'absolute', left: '50%', top: '64px', transform: 'translateX(-50%)', maxWidth: 'min(620px, 92%)',
            background: 'rgba(60, 44, 8, 0.94)', color: '#FFE9A8', border: '1px solid rgba(255, 214, 10, 0.5)', borderRadius: '6px',
            padding: '8px 12px', fontSize: '12px', lineHeight: 1.45, zIndex: 12, display: 'flex', gap: '10px', alignItems: 'flex-start'
          }}
        >
          <div style={{ flex: 1 }}>
            <strong>Partial view: {Math.round(qualityReport.coverage.angular_span_deg)}° of 360° filmed.</strong>{' '}
            {qualityReport.coverage.message}
            {qualityReport.coverage.recommendation && (<div style={{ marginTop: 4 }}><strong>Next flight:</strong> {qualityReport.coverage.recommendation}</div>)}
          </div>
          <button onClick={() => setCoverageDismissed(true)} title="Dismiss" style={{ background: 'none', border: 'none', color: '#FFE9A8', cursor: 'pointer', padding: 0 }}>
            <X size={14} />
          </button>
        </div>
      )}

      {/* Presentation bar: turntable, drone fly-through, mini-map, share link, fullscreen */}
      <div
        style={{
          position: 'absolute', left: '12px', bottom: '56px', display: 'flex', alignItems: 'center', gap: '2px',
          backgroundColor: 'rgba(23, 26, 32, 0.92)', backdropFilter: 'blur(8px)', padding: '3px 4px', borderRadius: '6px',
          border: '1px solid rgba(255, 255, 255, 0.12)', zIndex: 10
        }}
      >
        <button
          onClick={() => { setFlying(false); setAutoRotate(v => !v); }}
          title="Auto-rotate turntable (click the model to stop)"
          style={{ background: autoRotate ? 'rgba(167,237,121,0.18)' : 'none', border: 'none', cursor: 'pointer', color: autoRotate ? '#a7ed79' : '#BAC0CB', padding: '5px 7px', borderRadius: '4px', display: 'flex', alignItems: 'center' }}
        >
          <RotateCw size={15} />
        </button>
        <button
          onClick={() => { setAutoRotate(false); setFlying(v => !v); }}
          title="Fly through the drone's flight path (needs the flight path data)"
          style={{ background: flying ? 'rgba(167,237,121,0.18)' : 'none', border: 'none', cursor: 'pointer', color: flying ? '#a7ed79' : '#BAC0CB', padding: '5px 7px', borderRadius: '4px', display: 'flex', alignItems: 'center' }}
        >
          {flying ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <button
          onClick={() => setShowMiniMap(v => !v)}
          title="Show / hide the top-down mini-map"
          style={{ background: showMiniMap ? 'rgba(167,237,121,0.18)' : 'none', border: 'none', cursor: 'pointer', color: showMiniMap ? '#a7ed79' : '#BAC0CB', padding: '5px 7px', borderRadius: '4px', display: 'flex', alignItems: 'center' }}
        >
          <MapIcon size={15} />
        </button>
        <button
          onClick={copyViewLink}
          title="Copy a link to this exact view"
          style={{ background: false ? 'rgba(167,237,121,0.18)' : 'none', border: 'none', cursor: 'pointer', color: false ? '#a7ed79' : '#BAC0CB', padding: '5px 7px', borderRadius: '4px', display: 'flex', alignItems: 'center' }}
        >
          <Link2 size={15} />
        </button>
        <button
          onClick={toggleFullscreen}
          title="Fullscreen"
          style={{ background: isFullscreen ? 'rgba(167,237,121,0.18)' : 'none', border: 'none', cursor: 'pointer', color: isFullscreen ? '#a7ed79' : '#BAC0CB', padding: '5px 7px', borderRadius: '4px', display: 'flex', alignItems: 'center' }}
        >
          {isFullscreen ? <Minimize size={15} /> : <Maximize size={15} />}
        </button>
      </div>

      {showMiniMap && (
        <canvas
          ref={miniMapRef}
          width={180}
          height={180}
          title="Top-down map: green = drone path, yellow = your viewpoint"
          style={{
            position: 'absolute', right: '12px', bottom: '56px', width: '180px', height: '180px', borderRadius: '6px',
            border: '1px solid rgba(255, 255, 255, 0.18)', zIndex: 10
          }}
        />
      )}

      {toast && (
        <div style={{
          position: 'absolute', left: '50%', bottom: '100px', transform: 'translateX(-50%)', background: 'rgba(23,26,32,0.95)',
          color: '#fff', fontSize: '12px', padding: '6px 12px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.18)', zIndex: 20
        }}>
          {toast}
        </div>
      )}

      {/* Point Cloud Styling Slider (Visible in Points Mode) */}
      {displayMode === 'points' && (
        <div
          style={{
            position: 'absolute',
            top: '104px',
            left: '12px',
            backgroundColor: 'rgba(23, 26, 32, 0.9)',
            backdropFilter: 'blur(8px)',
            padding: '6px 12px',
            borderRadius: '6px',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            zIndex: 10,
            fontSize: '11px',
            color: '#BAC0CB'
          }}
        >
          <span>Point Size: {pointSize.toFixed(1)}px</span>
          <input
            type="range"
            min="1"
            max="8"
            step="0.5"
            value={pointSize}
            onChange={(e) => setPointSize(parseFloat(e.target.value))}
            style={{ width: '70px', cursor: 'pointer' }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={sizeAttenuation}
              onChange={(e) => setSizeAttenuation(e.target.checked)}
            />
            <span>Perspective scale</span>
          </label>
        </div>
      )}

      {/* Lighting / Sun Shadow Adjuster Popover */}
      {showLightingControls && (
        <div
          style={{
            position: 'absolute',
            top: '56px',
            left: '260px',
            backgroundColor: 'rgba(23, 26, 32, 0.95)',
            backdropFilter: 'blur(8px)',
            padding: '10px 14px',
            borderRadius: '6px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            zIndex: 10,
            fontSize: '11px',
            color: '#BAC0CB',
            boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
            minWidth: '200px'
          }}
        >
          <div style={{ fontWeight: 700, color: '#F7F8FA', display: 'flex', justifyContent: 'space-between' }}>
            <span>Sunlight & Shadow Angle</span>
            <X size={13} style={{ cursor: 'pointer' }} onClick={() => setShowLightingControls(false)} />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
              <span>Azimuth: {sunAzimuth}°</span>
            </div>
            <input
              type="range"
              min="0"
              max="360"
              value={sunAzimuth}
              onChange={(e) => setSunAzimuth(parseInt(e.target.value))}
              style={{ width: '100%', cursor: 'pointer' }}
            />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
              <span>Altitude: {sunElevation}°</span>
            </div>
            <input
              type="range"
              min="10"
              max="85"
              value={sunElevation}
              onChange={(e) => setSunElevation(parseInt(e.target.value))}
              style={{ width: '100%', cursor: 'pointer' }}
            />
          </div>
        </div>
      )}

      {/* Measurement HUD when active */}
      {measureMode && (
        <div
          style={{
            position: 'absolute',
            top: '104px',
            left: '12px',
            backgroundColor: 'rgba(23, 26, 32, 0.92)',
            backdropFilter: 'blur(8px)',
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid #ffeb3b',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            zIndex: 10,
            fontSize: '12px',
            color: '#F7F8FA'
          }}
        >
          <div>
            <span style={{ color: '#ffeb3b', fontWeight: 700 }}>3D Measurement Tool: </span>
            {measurePoints.length === 0 && 'Click on the terrain to set Point A'}
            {measurePoints.length === 1 && 'Click on the terrain to set Point B'}
            {measurePoints.length === 2 && (
              <span>
                Distance = <strong style={{ color: '#00e676' }}>{((measureDistance ?? 0) * geoScale).toFixed(2)}{isCalibrated ? ' m' : ' (relative units)'}</strong>
                {!gpsCalibrated && (
                  <span style={{ marginLeft: 10 }}>
                    · real length&nbsp;
                    <input
                      value={knownLength} onChange={(e) => setKnownLength(e.target.value)} placeholder="metres"
                      style={{ width: 64, fontSize: 11, padding: '2px 4px', borderRadius: 3, border: '1px solid rgba(255,255,255,.3)', background: '#0d1117', color: '#fff' }}
                    />
                    <button
                      onClick={() => {
                        const real = Number(knownLength);
                        if (!(real > 0) || !measureDistance) return;
                        const sc = real / measureDistance;
                        setUserScale(sc);
                        try { localStorage.setItem(`birdseye_scale_${projectId}`, String(sc)); } catch { /* ignore */ }
                      }}
                      style={{ marginLeft: 4, padding: '2px 8px', fontSize: 11, borderRadius: 3, border: '1px solid #A7ED79', background: 'rgba(167,237,121,.2)', color: '#A7ED79', cursor: 'pointer' }}
                    >Set scale</button>
                    {userScale != null && (
                      <button
                        onClick={() => { setUserScale(null); try { localStorage.removeItem(`birdseye_scale_${projectId}`); } catch { /* ignore */ } }}
                        style={{ marginLeft: 4, padding: '2px 6px', fontSize: 11, borderRadius: 3, border: '1px solid rgba(255,255,255,.3)', background: 'transparent', color: '#fff', cursor: 'pointer' }}
                      >Reset</button>
                    )}
                  </span>
                )}
              </span>
            )}
          </div>
          <button
            onClick={clearMeasurement}
            style={{
              padding: '2px 6px',
              fontSize: '10px',
              backgroundColor: 'rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '3px',
              color: '#FFFFFF',
              cursor: 'pointer'
            }}
          >
            Clear
          </button>
        </div>
      )}

      {/* Elevation Colorbar Legend (Bottom Right) */}
      {colorMode === 'elevation' && stats.elevationSpan !== '--' && (
        <div
          style={{
            position: 'absolute',
            bottom: '12px',
            right: '12px',
            backgroundColor: 'rgba(23, 26, 32, 0.92)',
            backdropFilter: 'blur(8px)',
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            fontSize: '11px',
            color: '#BAC0CB',
            zIndex: 10,
            boxShadow: '0 4px 12px rgba(0,0,0,0.35)'
          }}
        >
          <div style={{ fontWeight: 700, color: '#F7F8FA', fontSize: '11px' }}>Elevation Relief</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '14px',
                height: '80px',
                borderRadius: '3px',
                background: 'linear-gradient(to top, #1a3680 0%, #17a2b8 25%, #28a745 50%, #ffc107 75%, #fd7e14 90%, #d92534 100%)',
                border: '1px solid rgba(255,255,255,0.2)'
              }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '80px', fontSize: '10px', fontFamily: 'monospace' }}>
              <span style={{ color: '#d92534', fontWeight: 700 }}>+{(stats.maxZ * geoScale / vertExag).toFixed(1)}{unitElev}</span>
              <span style={{ color: '#28a745' }}>{(((stats.maxZ + stats.minZ) / 2) * geoScale / vertExag).toFixed(1)}{unitElev}</span>
              <span style={{ color: '#17a2b8', fontWeight: 700 }}>{(stats.minZ * geoScale / vertExag).toFixed(1)}{unitElev}</span>
            </div>
          </div>
        </div>
      )}

      {/* Bottom Left Statistics HUD */}
      <div
        style={{
          position: 'absolute',
          bottom: '12px',
          left: '12px',
          backgroundColor: 'rgba(23, 26, 32, 0.92)',
          backdropFilter: 'blur(8px)',
          padding: '8px 14px',
          borderRadius: '6px',
          border: '1px solid rgba(255, 255, 255, 0.12)',
          fontSize: '11px',
          color: '#BAC0CB',
          display: 'flex',
          alignItems: 'center',
          gap: '14px',
          zIndex: 10,
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.35)'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ color: '#7E8694' }}>Source: </span>
          <span
            className="mono"
            style={{
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '10px',
              backgroundColor: targetFile?.filename === 'dense_cloud.ply'
                ? 'rgba(39, 174, 96, 0.25)'
                : targetFile?.filename === 'sparse_cloud.ply'
                  ? 'rgba(52, 152, 219, 0.25)'
                  : 'rgba(243, 156, 18, 0.25)',
              color: targetFile?.filename === 'dense_cloud.ply'
                ? '#2ecc71'
                : targetFile?.filename === 'sparse_cloud.ply'
                  ? '#5dade2'
                  : '#f39c12',
              border: '1px solid rgba(255,255,255,0.1)'
            }}
          >
            {getSourceLabel()}
          </span>
        </div>
        <div>
          <span style={{ color: '#7E8694' }}>Points: </span>
          <span className="mono" style={{ fontWeight: 700, color: 'var(--accent-lime)' }}>
            {stats.points.toLocaleString()}
          </span>
        </div>
        <div>
          <span style={{ color: '#7E8694' }}>Faces: </span>
          <span className="mono" style={{ fontWeight: 700, color: '#F7F8FA' }}>
            {stats.faces.toLocaleString()}
          </span>
        </div>
        <div>
          <span style={{ color: '#7E8694' }}>Extents: </span>
          <span className="mono" style={{ color: '#F7F8FA' }}>{boundsText}</span>
        </div>
        <div>
          <span style={{ color: '#7E8694' }}>Elevation: </span>
          <span className="mono" style={{ color: '#F7F8FA' }}>{elevText}</span>
        </div>
      </div>

      {/* Empty State */}
      {!targetFile && !isLoading && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            color: '#BAC0CB',
            pointerEvents: 'none',
            backgroundColor: '#181B20'
          }}
        >
          <Box size={44} color="var(--accent-lime)" style={{ opacity: 0.8 }} />
          <div style={{ fontSize: '16px', fontWeight: 700, color: '#F7F8FA' }}>
            No 3D Terrain Model Reconstructed Yet
          </div>
          <div style={{ fontSize: '13px', color: '#7E8694', maxWidth: '380px', textAlign: 'center', lineHeight: 1.5 }}>
            Upload or pick a drone video in the Video Intake tab, then execute the reconstruction pipeline to inspect the processed 3D terrain.
          </div>
        </div>
      )}

      {/* Loading Overlay */}
      {isLoading && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(24, 27, 32, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            color: '#F7F8FA',
            zIndex: 20
          }}
        >
          <div
            style={{
              width: '36px',
              height: '36px',
              border: '3px solid rgba(167, 237, 121, 0.2)',
              borderTopColor: 'var(--accent-lime)',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite'
            }}
          />
          <div style={{ fontSize: '13px', fontWeight: 600 }}>{loadingProgress || 'Loading 3D Terrain...'}</div>
        </div>
      )}

      {/* Error Notice */}
      {errorMsg && (
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            backgroundColor: 'rgba(168, 50, 61, 0.95)',
            padding: '16px 22px',
            borderRadius: '6px',
            color: '#FFFFFF',
            fontSize: '13px',
            maxWidth: '420px',
            textAlign: 'center',
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            zIndex: 20
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: '4px' }}>Failed to Load 3D Model</div>
          <div style={{ fontSize: '12px', opacity: 0.9 }}>{errorMsg}</div>
        </div>
      )}

    </div>
  );
};
