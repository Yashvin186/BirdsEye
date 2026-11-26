import React, { useState, useRef, useEffect } from 'react';
import { VideoMetadata, PipelineConfigRequest } from '../../types';
import { uploadVideo, uploadTelemetry, importImageFolder, loadSampleVideo, fetchSampleVideos } from '../../api/client';
import { UploadCloud, Video, CheckCircle, AlertTriangle, Settings, Sliders, Play, FileText, Sparkles } from 'lucide-react';

interface Props {
  projectId: string;
  existingMetadata: VideoMetadata | null;
  capabilities?: any;
  onVideoUploaded: (meta: VideoMetadata) => void;
  onStartReconstruction: (config: PipelineConfigRequest) => void;
  isProcessing: boolean;
}

export const VideoUploadCard: React.FC<Props> = ({
  projectId,
  existingMetadata,
  capabilities,
  onVideoUploaded,
  onStartReconstruction,
  isProcessing,
}) => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(existingMetadata);
  const [sampleVideos, setSampleVideos] = useState<Array<{ name: string; size_mb: number }>>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const srtInputRef = useRef<HTMLInputElement>(null);
  const [telemetry, setTelemetry] = useState<string | null>(null);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);

  const handleTelemetry = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    setTelemetryError(null);
    try {
      const r = await uploadTelemetry(projectId, f);
      setTelemetry(`${r.filename}: ${r.samples} GPS samples over ${r.duration_s}s`);
    } catch (err: any) {
      setTelemetry(null);
      setTelemetryError(err.message || 'Could not read the flight log');
    }
  };

  useEffect(() => {
    fetchSampleVideos().then(setSampleVideos).catch(() => {});
  }, []);

  const handleSelectSample = async (sampleName: string) => {
    setIsUploading(true);
    setUploadError(null);
    try {
      const meta = await loadSampleVideo(projectId, sampleName);
      setMetadata(meta);
      onVideoUploaded(meta);
    } catch (err: any) {
      setUploadError(err.message || 'Failed to load sample video');
    } finally {
      setIsUploading(false);
    }
  };

  // Reconstruction Pipeline Parameters
  const [config, setConfig] = useState<PipelineConfigRequest>({
    sampling_fps: 2.0,
    max_frames: 140,
    blur_threshold: 80.0,
    similarity_threshold: 0.985,
    matching_strategy: 'sequential',
    gpu_mode: 'auto',
    enable_dense_mvs: true,
    enable_ai_depth: false,
    enable_meshing: true,
    quality_preset: 'balanced',
    fill_unseen_regions: false,
    isolate_subject: true,
    cpu_stereo_fallback: true,
    scene_mode: 'auto',
  });

  const [showAdvanced, setShowAdvanced] = useState(false);

  const [folderPath, setFolderPath] = useState('');
  const [folderMax, setFolderMax] = useState(200);
  const handleImportFolder = async () => {
    if (!folderPath.trim()) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const meta = await importImageFolder(projectId, folderPath.trim(), folderMax);
      setMetadata(meta);
      onVideoUploaded(meta);
    } catch (err: any) {
      setUploadError(err.message || 'Failed to import the image folder');
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const meta = await uploadVideo(projectId, file);
      setMetadata(meta);
      onVideoUploaded(meta);
    } catch (err: any) {
      setUploadError(err.message || 'Failed to upload video');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const meta = await uploadVideo(projectId, file);
      setMetadata(meta);
      onVideoUploaded(meta);
    } catch (err: any) {
      setUploadError(err.message || 'Failed to upload video');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      
      {/* Upload Zone */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => !metadata && fileInputRef.current?.click()}
        style={{
          border: '2px dashed var(--border-strong)',
          borderRadius: '6px',
          padding: metadata ? '16px 20px' : '40px 20px',
          backgroundColor: metadata ? '#F0F1F3' : '#D7D9DE',
          textAlign: 'center',
          cursor: metadata ? 'default' : 'pointer',
          transition: 'all 0.2s ease'
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp4,.mov,.avi,.mkv"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        {!metadata ? (
          <div>
            <UploadCloud size={36} color="#4D5258" style={{ margin: '0 auto 12px auto' }} />
            <div style={{ fontSize: '15px', fontWeight: 700, color: '#171A20' }}>
              {isUploading ? 'Uploading & inspecting video frames...' : 'Drag & drop drone video, or browse'}
            </div>
            <div style={{ fontSize: '12px', color: '#606773', marginTop: '4px' }}>
              Accepted formats: MP4, MOV (Continuous single-pass flight recommended)
            </div>

            {/* Quick-load Sample Footage */}
            {sampleVideos.length > 0 && (
              <div 
                onClick={(e) => e.stopPropagation()} 
                style={{ 
                  marginTop: '16px', 
                  paddingTop: '16px', 
                  borderTop: '1px solid rgba(0,0,0,0.08)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '8px'
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 600, color: '#4D5258', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Sparkles size={13} color="#2F7018" /> Or quick-load sample drone footage:
                </div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
                  {sampleVideos.map((s) => (
                    <button
                      key={s.name}
                      type="button"
                      disabled={isUploading}
                      onClick={() => handleSelectSample(s.name)}
                      style={{
                        padding: '6px 12px',
                        backgroundColor: '#FFFFFF',
                        border: '1px solid #BAC0CB',
                        borderRadius: '4px',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#171A20',
                        cursor: isUploading ? 'not-allowed' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                        transition: 'all 0.15s ease'
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#171A20')}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#BAC0CB')}
                    >
                      <Video size={13} color="#2F7018" />
                      <span>{s.name}</span>
                      <span style={{ fontSize: '10px', color: '#7E8694' }}>({s.size_mb} MB)</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {uploadError && (
              <div style={{ color: 'var(--status-error)', fontSize: '12px', marginTop: '10px', fontWeight: 600 }}>
                {uploadError}
              </div>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', textAlign: 'left' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{
                width: '40px',
                height: '40px',
                backgroundColor: 'var(--status-success-bg)',
                color: 'var(--status-success)',
                borderRadius: '4px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Video size={22} />
              </div>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 700, color: '#171A20' }}>
                  {metadata.original_filename}
                </div>
                <div style={{ fontSize: '12px', color: '#606773' }}>
                  {metadata.width}x{metadata.height} &bull; {metadata.fps} FPS &bull; {metadata.duration_seconds}s duration &bull; {(metadata.size_bytes / (1024 * 1024)).toFixed(1)} MB
                </div>
              </div>
            </div>
            <button
              onClick={() => { setMetadata(null); fileInputRef.current?.click(); }}
              className="btn btn-outline"
              style={{ fontSize: '12px', padding: '6px 12px' }}
            >
              Replace Video
            </button>
          </div>
        )}
      </div>

      {/* Alternative input: a folder of frames already on this computer (no upload needed) */}
      <div style={{ border: '1px solid var(--border-light)', borderRadius: '4px', padding: '16px', backgroundColor: '#fff' }}>
        <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '6px', textTransform: 'uppercase', color: '#3D424B' }}>
          Or use a folder of frames (JPG / PNG)
        </h3>
        <p style={{ fontSize: '12px', color: '#5C5E62', marginBottom: 10 }}>
          Paste the folder path (e.g. a Tanks and Temples sequence or frames exported from a video). It is read in place - nothing is uploaded.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            value={folderPath} onChange={(e) => setFolderPath(e.target.value)}
            placeholder="C:\\data\\Ignatius\\images   or   /home/me/Ignatius"
            style={{ flex: 1, minWidth: 240, padding: '8px 10px', fontSize: 12, border: '1px solid var(--border-light)', borderRadius: 4 }}
          />
          <label style={{ fontSize: 12, color: '#3D424B' }}>
            max images{' '}
            <input type="number" min={10} max={1000} value={folderMax} onChange={(e) => setFolderMax(Number(e.target.value) || 200)}
              style={{ width: 70, padding: '6px', fontSize: 12, border: '1px solid var(--border-light)', borderRadius: 4 }} />
          </label>
          <button onClick={handleImportFolder} disabled={isUploading || !folderPath.trim()} className="btn btn-primary" style={{ fontSize: 12, padding: '8px 14px' }}>
            Import folder
          </button>
        </div>
      </div>

      {/* Drone flight log (GPS) -> real-metre scale */}
      {metadata && (
        <div style={{ border: '1px solid var(--border-strong)', borderRadius: '6px', padding: '12px 16px', background: '#F7F8FA', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#171A20' }}>Drone flight log (optional, recommended)</div>
            <div style={{ fontSize: '12px', color: '#606773', marginTop: 2 }}>
              Add the <strong>.SRT</strong> file the drone saved next to the video. It gives the model real-metre scale and a north-up map, so you can measure in metres.
            </div>
            {telemetry && <div style={{ fontSize: '12px', color: '#2F7018', fontWeight: 600, marginTop: 4 }}>✓ {telemetry}</div>}
            {telemetryError && <div style={{ fontSize: '12px', color: 'var(--status-error)', fontWeight: 600, marginTop: 4 }}>{telemetryError}</div>}
          </div>
          <input ref={srtInputRef} type="file" accept=".srt" style={{ display: 'none' }} onChange={handleTelemetry} />
          <button type="button" className="btn btn-outline" style={{ fontSize: '12px', padding: '6px 12px' }} onClick={() => srtInputRef.current?.click()}>
            {telemetry ? 'Replace .SRT' : 'Add .SRT file'}
          </button>
        </div>
      )}

      {/* Mission type + capture guide (from photogrammetry capture guidance) */}
      {metadata && (
        <div style={{ border: '1px solid var(--border-light)', borderRadius: '4px', padding: '16px', backgroundColor: '#fff' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '10px', textTransform: 'uppercase', color: '#3D424B' }}>
            What did you film?
          </h3>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            {([
              ['auto', 'Auto-detect'],
              ['aerial', 'Terrain / site map (straight down)'],
              ['object', 'Structure / object (orbit)'],
            ] as const).map(([val, label]) => (
              <button
                key={val}
                type="button"
                onClick={() => setConfig({ ...config, scene_mode: val })}
                style={{
                  padding: '8px 12px', fontSize: '12px', fontWeight: 600, cursor: 'pointer', borderRadius: 4,
                  border: config.scene_mode === val ? '2px solid #3E6AE1' : '1px solid var(--border-light)',
                  backgroundColor: config.scene_mode === val ? '#EAF0FD' : '#fff', color: '#171A20',
                }}
              >{label}</button>
            ))}
          </div>
          <div style={{ fontSize: '12px', color: '#5C5E62', lineHeight: 1.6 }}>
            <strong>Best results:</strong> keep ONE continuous shot (no cuts or fades) · overlap consecutive views by 75% or more ·
            steady altitude and camera angle · fly slowly, avoid sharp turns.<br />
            <strong>Terrain / roofs:</strong> lawn-mower grid with the camera pointing straight down. <strong>Walls / structures:</strong> slow
            orbit around it with the camera tilted ~45°, then a second lower circle. Add the drone's .SRT file for real-world scale.
          </div>
        </div>
      )}

      {/* Preflight Metadata & Warnings */}
      {metadata && (
        <div style={{
          backgroundColor: '#F0F1F3',
          border: '1px solid var(--border-light)',
          borderRadius: '4px',
          padding: '16px'
        }}>
          <h3 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase', color: '#3D424B' }}>
            Preflight Inspection Checklist
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '14px' }}>
            <div style={{ padding: '8px 10px', backgroundColor: '#D7D9DE', borderRadius: '4px' }}>
              <span style={{ fontSize: '10px', fontWeight: 700, color: '#606773', textTransform: 'uppercase' }}>Resolution</span>
              <div style={{ fontSize: '13px', fontWeight: 700 }}>{metadata.width} × {metadata.height}</div>
            </div>
            <div style={{ padding: '8px 10px', backgroundColor: '#D7D9DE', borderRadius: '4px' }}>
              <span style={{ fontSize: '10px', fontWeight: 700, color: '#606773', textTransform: 'uppercase' }}>Frame Rate</span>
              <div style={{ fontSize: '13px', fontWeight: 700 }}>{metadata.fps} FPS</div>
            </div>
            <div style={{ padding: '8px 10px', backgroundColor: '#D7D9DE', borderRadius: '4px' }}>
              <span style={{ fontSize: '10px', fontWeight: 700, color: '#606773', textTransform: 'uppercase' }}>Codec</span>
              <div style={{ fontSize: '13px', fontWeight: 700 }}>{metadata.codec}</div>
            </div>
            <div style={{ padding: '8px 10px', backgroundColor: '#D7D9DE', borderRadius: '4px' }}>
              <span style={{ fontSize: '10px', fontWeight: 700, color: '#606773', textTransform: 'uppercase' }}>GPS Prior</span>
              <div style={{ fontSize: '13px', fontWeight: 700, color: metadata.has_gps ? 'var(--status-success)' : '#606773' }}>
                {metadata.has_gps ? 'Present' : 'None (Relative Scale)'}
              </div>
            </div>
          </div>

          {metadata.warnings.length > 0 && (
            <div style={{
              padding: '10px 12px',
              backgroundColor: '#F3DDAA',
              border: '1px solid #946414',
              borderRadius: '4px',
              color: '#4A3408',
              fontSize: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700 }}>
                <AlertTriangle size={14} color="#946414" />
                <span>Preflight Warnings</span>
              </div>
              {metadata.warnings.map((w, idx) => (
                <div key={idx}>&bull; {w}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Sampling & Photogrammetry Configuration */}
      <div style={{
        backgroundColor: '#F0F1F3',
        border: '1px solid var(--border-light)',
        borderRadius: '4px',
        padding: '16px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sliders size={16} color="#34383E" />
            <h3 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', color: '#3D424B' }}>
              Reconstruction Pipeline Settings
            </h3>
          </div>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="btn btn-outline"
            style={{ fontSize: '11px', padding: '4px 8px' }}
          >
            {showAdvanced ? 'Hide Advanced' : 'Show Advanced'}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '14px' }}>
          <div>
            <label style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', display: 'block', marginBottom: '4px' }}>
              Target Sampling Rate ({config.sampling_fps} FPS)
            </label>
            <input
              type="range"
              min="0.5"
              max="5.0"
              step="0.5"
              value={config.sampling_fps}
              onChange={(e) => setConfig({ ...config, sampling_fps: parseFloat(e.target.value) })}
              style={{ width: '100%' }}
            />
            <div style={{ fontSize: '11px', color: '#606773', marginTop: '2px' }}>
              Extracts ~{config.sampling_fps} frames for each second of video.
            </div>
          </div>

          <div>
            <label style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', display: 'block', marginBottom: '4px' }}>
              Max Candidate Frames ({config.max_frames})
            </label>
            <input
              type="range"
              min="30"
              max="400"
              step="10"
              value={config.max_frames}
              onChange={(e) => setConfig({ ...config, max_frames: parseInt(e.target.value, 10) })}
              style={{ width: '100%' }}
            />
            <div style={{ fontSize: '11px', color: '#606773', marginTop: '2px' }}>
              Limits total keyframes to prevent excessive computation.
            </div>
          </div>
        </div>

        {/* Hardware Acceleration & Power Card */}
        <div style={{
          backgroundColor: '#F9FAFB',
          border: '1px solid var(--border-light)',
          borderRadius: '6px',
          padding: '12px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#171A20' }}>
              Hardware Engine & Battery Protection
            </span>
            {capabilities?.power_status && (
              <span style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '3px 8px',
                borderRadius: '12px',
                backgroundColor: capabilities.power_status.on_battery ? '#FEF3C7' : '#D1FAE5',
                color: capabilities.power_status.on_battery ? '#B45309' : '#065F46'
              }}>
                {capabilities.power_status.status_text}
              </span>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
            <div
              onClick={() => setConfig({ ...config, gpu_mode: 'auto' })}
              style={{
                padding: '10px',
                borderRadius: '4px',
                border: (config.gpu_mode === 'auto' || !config.gpu_mode) ? '2px solid var(--accent-slate)' : '1px solid var(--border-light)',
                backgroundColor: (config.gpu_mode === 'auto' || !config.gpu_mode) ? '#EFF6FF' : '#FFFFFF',
                cursor: 'pointer'
              }}
            >
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#171A20' }}>Auto-Detect Mode</div>
              <div style={{ fontSize: '11px', color: '#606773', marginTop: '2px' }}>
                CUDA with charger; auto-switches to CPU on battery.
              </div>
            </div>

            <div
              onClick={() => setConfig({ ...config, gpu_mode: 'cuda' })}
              style={{
                padding: '10px',
                borderRadius: '4px',
                border: config.gpu_mode === 'cuda' ? '2px solid var(--accent-slate)' : '1px solid var(--border-light)',
                backgroundColor: config.gpu_mode === 'cuda' ? '#EFF6FF' : '#FFFFFF',
                cursor: 'pointer'
              }}
            >
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#171A20' }}>NVIDIA GPU (CUDA)</div>
              <div style={{ fontSize: '11px', color: '#606773', marginTop: '2px' }}>
                High-speed stereo MVS. Use when plugged into charger.
              </div>
            </div>

            <div
              onClick={() => setConfig({ ...config, gpu_mode: 'cpu' })}
              style={{
                padding: '10px',
                borderRadius: '4px',
                border: config.gpu_mode === 'cpu' ? '2px solid var(--accent-slate)' : '1px solid var(--border-light)',
                backgroundColor: config.gpu_mode === 'cpu' ? '#EFF6FF' : '#FFFFFF',
                cursor: 'pointer'
              }}
            >
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#171A20' }}>CPU Safe Mode</div>
              <div style={{ fontSize: '11px', color: '#606773', marginTop: '2px' }}>
                Pure CPU processing. Never fails on battery power.
              </div>
            </div>
          </div>
        </div>

        {showAdvanced && (
          <div style={{ marginTop: '14px', paddingTop: '14px', borderTop: '1px solid var(--border-light)', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', display: 'block', marginBottom: '4px' }}>
                Blur Threshold ({config.blur_threshold})
              </label>
              <input
                type="number"
                value={config.blur_threshold}
                onChange={(e) => setConfig({ ...config, blur_threshold: parseFloat(e.target.value) })}
                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid var(--border-strong)' }}
              />
              <div style={{ fontSize: '11px', color: '#606773', marginTop: '2px' }}>
                Laplacian variance threshold. Lower values allow softer frames.
              </div>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', display: 'block', marginBottom: '4px' }}>
                Stationary Filter ({config.similarity_threshold})
              </label>
              <input
                type="number"
                step="0.005"
                min="0.80"
                max="0.999"
                value={config.similarity_threshold}
                onChange={(e) => setConfig({ ...config, similarity_threshold: parseFloat(e.target.value) })}
                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid var(--border-strong)' }}
              />
              <div style={{ fontSize: '11px', color: '#606773', marginTop: '2px' }}>
                Spatial similarity limit. Rejects near-identical frames when hovering.
              </div>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', display: 'block', marginBottom: '4px' }}>
                Matching Strategy
              </label>
              <select
                value={config.matching_strategy}
                onChange={(e) => setConfig({ ...config, matching_strategy: e.target.value as any })}
                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid var(--border-strong)' }}
              >
                <option value="sequential">Sequential Matching (Optimal for continuous drone video)</option>
                <option value="exhaustive">Exhaustive Matching (Pairwise all frames)</option>
              </select>
            </div>

            <div style={{ gridColumn: 'span 3' }}>
              <label style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', display: 'block', marginBottom: '4px' }}>
                Quality preset
              </label>
              <select
                value={config.quality_preset ?? 'balanced'}
                onChange={(e) => setConfig({ ...config, quality_preset: e.target.value as 'fast' | 'balanced' | 'high' })}
                style={{ width: '100%', padding: '6px', borderRadius: '4px', border: '1px solid var(--border-strong)' }}
              >
                <option value="fast">Fast: quick preview (smaller images, fewer frames)</option>
                <option value="balanced">Balanced: recommended</option>
                <option value="high">High: slowest, sharpest when zoomed in</option>
              </select>
            </div>

            <div style={{ gridColumn: 'span 3', display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
              <input
                type="checkbox"
                id="enable_ai_depth"
                checked={!!config.enable_ai_depth}
                onChange={(e) => setConfig({ ...config, enable_ai_depth: e.target.checked })}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <label htmlFor="enable_ai_depth" style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', cursor: 'pointer' }}>
                Enable AI Depth Completion (Depth Anything V2) — fills low-texture or reflective areas that ARE visible in the video (cannot recover hidden sides). Leave OFF for accurate measuring: it adds noisy, blocky points.
              </label>
            </div>

            <div style={{ gridColumn: 'span 3', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="checkbox"
                id="isolate_subject"
                checked={config.isolate_subject !== false}
                onChange={(e) => setConfig({ ...config, isolate_subject: e.target.checked })}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <label htmlFor="isolate_subject" style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', cursor: 'pointer' }}>
                Isolate the subject — remove distant background (mountains, sky, river) that otherwise becomes giant stretched sheets
              </label>
            </div>

            <div style={{ gridColumn: 'span 3', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="checkbox"
                id="cpu_stereo_fallback"
                checked={config.cpu_stereo_fallback !== false}
                onChange={(e) => setConfig({ ...config, cpu_stereo_fallback: e.target.checked })}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <label htmlFor="cpu_stereo_fallback" style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', cursor: 'pointer' }}>
                CPU stereo fallback — build a dense cloud even without an NVIDIA GPU (noisier than GPU MVS)
              </label>
            </div>

            <div style={{ gridColumn: 'span 3', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="checkbox"
                id="fill_unseen_regions"
                checked={!!config.fill_unseen_regions}
                onChange={(e) => setConfig({ ...config, fill_unseen_regions: e.target.checked })}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <label htmlFor="fill_unseen_regions" style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', cursor: 'pointer' }}>
                Close surfaces over regions the video never saw (undersides, hidden sides) — looks complete, but those parts are extrapolated, not measured. Leave OFF for accurate measuring.
              </label>
            </div>
          </div>
        )}
      </div>

      {/* Start Button */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={() => onStartReconstruction(config)}
          disabled={!metadata || isProcessing}
          className="btn btn-primary"
          style={{ padding: '12px 24px', fontSize: '14px' }}
        >
          <Play size={16} fill="#171A20" />
          <span>{isProcessing ? 'Reconstruction in Progress...' : 'Start 3D Reconstruction'}</span>
        </button>
      </div>

    </div>
  );
};
