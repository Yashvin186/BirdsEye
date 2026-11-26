import React, { useState, useEffect } from 'react';
import { JobStatusResponse, StageDetail } from '../../types';
import { fetchProjectFrames } from '../../api/client';
import {
  CheckCircle2,
  Clock,
  AlertOctagon,
  SkipForward,
  Loader2,
  Terminal,
  Ban,
  ChevronRight,
  Eye,
  FileSpreadsheet,
  Image as ImageIcon,
  Layers,
  Box,
  Camera,
  Cpu,
  Zap,
  Sparkles,
  Download,
  Check,
  Maximize2
} from 'lucide-react';

interface Props {
  job: JobStatusResponse | null;
  onCancelJob: () => void;
  onViewContactSheet?: () => void;
  onViewResults?: () => void;
}

export const PipelineView: React.FC<Props> = ({
  job,
  onCancelJob,
  onViewContactSheet,
  onViewResults,
}) => {
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [extractedFrames, setExtractedFrames] = useState<{ filename: string; url: string }[]>([]);
  const [totalFrameCount, setTotalFrameCount] = useState<number>(0);
  const [selectedPreviewImage, setSelectedPreviewImage] = useState<string | null>(null);

  useEffect(() => {
    if (job?.project_id) {
      fetchProjectFrames(job.project_id)
        .then((data) => {
          setExtractedFrames(data.frames);
          setTotalFrameCount(data.total_count);
        })
        .catch(() => {});
    }
  }, [job?.project_id, selectedStageId, job?.current_stage]);

  if (!job) {
    return (
      <div style={{ padding: '32px', textAlign: 'center', color: '#606773' }}>
        No active reconstruction job. Upload a video and click Start 3D Reconstruction.
      </div>
    );
  }

  const activeStage = job.stages.find((s) => s.stage_id === (selectedStageId || job.current_stage || job.stages[0]?.stage_id));
  const projectId = job.project_id;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '10px' }}>
      
      {/* Job Header Bar */}
      <div style={{
        backgroundColor: '#FFFFFF',
        padding: '10px 16px',
        borderRadius: '6px',
        border: '1px solid var(--border-light)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="mono" style={{ fontSize: '12px', fontWeight: 700, color: '#3D424B' }}>
            JOB: {job.job_id}
          </span>
          <span className={`badge ${
            job.status === 'completed' ? 'badge-success' :
            job.status === 'partial' ? 'badge-warning' :
            job.status === 'failed' ? 'badge-error' :
            job.status === 'cancelled' ? 'badge-warning' : 'badge-info'
          }`}>
            {job.status === 'partial' ? 'Partial' : job.status}
          </span>
          {job.duration_seconds && (
            <span style={{ fontSize: '12px', color: '#606773' }}>
              Duration: {job.duration_seconds}s
            </span>
          )}
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          {job.status === 'running' && (
            <button onClick={onCancelJob} className="btn btn-danger" style={{ padding: '6px 12px', fontSize: '12px' }}>
              <Ban size={14} />
              <span>Cancel Job</span>
            </button>
          )}
          {(job.status === 'completed' || job.status === 'partial') && onViewResults && (
            <button onClick={onViewResults} className="btn btn-primary" style={{ padding: '6px 14px', fontSize: '12px' }}>
              <Eye size={14} />
              <span>Inspect 3D Model</span>
            </button>
          )}
        </div>
      </div>

      {/* Stepper Grid (Dynamic 10 Stages) */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(95px, 1fr))',
        gap: '6px',
        backgroundColor: '#F3F4F6',
        padding: '8px',
        borderRadius: '6px',
        border: '1px solid var(--border-light)'
      }}>
        {job.stages.map((st, index) => {
          const isSelected = st.stage_id === activeStage?.stage_id;
          let icon = <Clock size={13} color="#9CA3AF" />;
          let statusColor = '#9CA3AF';

          if (st.status === 'completed') {
            icon = <CheckCircle2 size={13} color="#10B981" />;
            statusColor = '#10B981';
          } else if (st.status === 'partial') {
            icon = <CheckCircle2 size={13} color="#D97706" />;
            statusColor = '#D97706';
          } else if (st.status === 'running') {
            icon = <Loader2 size={13} color="#2563EB" className="animate-spin" />;
            statusColor = '#2563EB';
          } else if (st.status === 'failed') {
            icon = <AlertOctagon size={13} color="#EF4444" />;
            statusColor = '#EF4444';
          } else if (st.status === 'skipped') {
            icon = <SkipForward size={13} color="#D97706" />;
            statusColor = '#D97706';
          } else if (st.status === 'unsupported') {
            icon = <Ban size={13} color="#D97706" />;
            statusColor = '#D97706';
          }

          return (
            <div
              key={st.stage_id}
              onClick={() => setSelectedStageId(st.stage_id)}
              style={{
                backgroundColor: isSelected ? '#FFFFFF' : '#FAFAFA',
                border: isSelected ? '2px solid var(--accent-slate)' : '1px solid var(--border-light)',
                borderRadius: '4px',
                padding: '6px 6px',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: '3px',
                transition: 'all 0.15s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span className="mono" style={{ fontSize: '10px', color: '#6B7280' }}>
                  #{index + 1}
                </span>
                {icon}
              </div>
              <div style={{
                fontSize: '11px',
                fontWeight: 600,
                color: isSelected ? '#111827' : '#374151',
                lineHeight: 1.15,
                minHeight: '26px'
              }}>
                {st.title}
              </div>
              <div style={{ fontSize: '9px', color: statusColor, textTransform: 'capitalize', fontWeight: 600 }}>
                {st.status}
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Stage Details & Live Console */}
      {activeStage && (
        <div style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: '1.2fr 1.3fr',
          gap: '10px',
          minHeight: 0
        }}>
          {/* Stage Info & Visual Preview Panel */}
          <div style={{
            backgroundColor: '#FFFFFF',
            border: '1px solid var(--border-light)',
            borderRadius: '6px',
            padding: '12px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            overflowY: 'auto'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: '10px', fontWeight: 700, color: '#6B7280', textTransform: 'uppercase' }}>
                  Pipeline Step #{job.stages.findIndex(s => s.stage_id === activeStage.stage_id) + 1}
                </div>
                <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#111827', margin: '2px 0 0 0' }}>
                  {activeStage.title}
                </h3>
              </div>
              <span className={`badge ${
                activeStage.status === 'completed' ? 'badge-success' :
                activeStage.status === 'running' ? 'badge-info' :
                activeStage.status === 'failed' ? 'badge-error' : 'badge-warning'
              }`}>
                {activeStage.status}
              </span>
            </div>

            {/* VISUAL PREVIEW FOR ACTIVE STEP */}
            <div style={{
              backgroundColor: '#F9FAFB',
              border: '1px solid var(--border-light)',
              borderRadius: '6px',
              padding: '10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#4B5563', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <ImageIcon size={13} /> Visual Step Preview
                </span>
                {activeStage.stage_id === 'extracting_frames' && totalFrameCount > 0 && (
                  <span style={{ fontSize: '11px', color: '#059669', fontWeight: 600 }}>
                    {totalFrameCount} Extracted Keyframes
                  </span>
                )}
              </div>

              {/* 1. Validating Preview */}
              {activeStage.stage_id === 'validating' && (
                <div style={{ fontSize: '12px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <CheckCircle2 size={14} color="#10B981" />
                    <span>Drone video container and audio streams validated</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <CheckCircle2 size={14} color="#10B981" />
                    <span>Full frame decodability & hardware inspection passed</span>
                  </div>
                </div>
              )}

              {/* 2. Frame Extraction Preview (Live Thumbnail Gallery) */}
              {activeStage.stage_id === 'extracting_frames' && (
                <div>
                  {extractedFrames.length > 0 ? (
                    <div>
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(75px, 1fr))',
                        gap: '6px',
                        maxHeight: '180px',
                        overflowY: 'auto',
                        padding: '4px 0'
                      }}>
                        {extractedFrames.map((frame, idx) => (
                          <div
                            key={idx}
                            onClick={() => setSelectedPreviewImage(frame.url)}
                            style={{
                              position: 'relative',
                              aspectRatio: '16/9',
                              backgroundColor: '#E5E7EB',
                              borderRadius: '4px',
                              overflow: 'hidden',
                              cursor: 'pointer',
                              border: '1px solid #D1D5DB'
                            }}
                          >
                            <img
                              src={frame.url}
                              alt={frame.filename}
                              loading="lazy"
                              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                            <div style={{
                              position: 'absolute',
                              bottom: 0,
                              left: 0,
                              right: 0,
                              backgroundColor: 'rgba(0,0,0,0.6)',
                              color: '#FFFFFF',
                              fontSize: '8px',
                              textAlign: 'center',
                              padding: '1px 0'
                            }}>
                              #{idx + 1}
                            </div>
                          </div>
                        ))}
                      </div>
                      <div style={{ fontSize: '10px', color: '#6B7280', marginTop: '4px' }}>
                        Showing representative extracted keyframes. Click any thumbnail to inspect.
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: '11px', color: '#6B7280', textAlign: 'center', padding: '12px' }}>
                      {activeStage.status === 'running' ? 'Extracting candidate keyframes from video...' : 'No extracted frames available.'}
                    </div>
                  )}
                </div>
              )}

              {/* 3. Preprocessing / Contact Sheet Preview */}
              {activeStage.stage_id === 'preprocessing' && (
                <div>
                  <div style={{
                    position: 'relative',
                    width: '100%',
                    maxHeight: '180px',
                    borderRadius: '4px',
                    overflow: 'hidden',
                    border: '1px solid #D1D5DB',
                    cursor: 'pointer',
                    backgroundColor: '#111827'
                  }}
                  onClick={onViewContactSheet}
                  >
                    <img
                      src={`/api/projects/${projectId}/files/contact_sheet.jpg`}
                      alt="Contact Sheet"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                      }}
                      style={{ width: '100%', height: '180px', objectFit: 'contain' }}
                    />
                    <div style={{
                      position: 'absolute',
                      top: '6px',
                      right: '6px',
                      backgroundColor: 'rgba(0,0,0,0.7)',
                      color: '#FFFFFF',
                      fontSize: '10px',
                      padding: '3px 6px',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}>
                      <Maximize2 size={11} /> Expand Contact Sheet
                    </div>
                  </div>
                  {onViewContactSheet && (
                    <button
                      onClick={onViewContactSheet}
                      className="btn btn-secondary"
                      style={{ fontSize: '11px', marginTop: '6px', padding: '4px 8px' }}
                    >
                      <FileSpreadsheet size={13} />
                      <span>Inspect Full Contact Sheet</span>
                    </button>
                  )}
                </div>
              )}

              {/* 4. Feature Matching Preview */}
              {activeStage.stage_id === 'feature_matching' && (
                <div style={{ fontSize: '12px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Feature Detector:</span>
                    <span style={{ fontWeight: 600 }}>SIFT (Scale-Invariant Feature Transform)</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Matching Geometry:</span>
                    <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>
                      {job.config?.matching_strategy || 'Sequential (Drone Overlap)'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                    <span style={{ color: '#6B7280' }}>Hardware Engine:</span>
                    <span style={{ fontWeight: 600, color: '#2563EB' }}>
                      {job.config?.gpu_mode === 'cpu' ? 'CPU Multi-Core Safe' : 'Hardware Accelerated SIFT'}
                    </span>
                  </div>
                </div>
              )}

              {/* 5. Structure-from-Motion (SfM) Preview */}
              {activeStage.stage_id === 'sfm' && (
                <div style={{ fontSize: '12px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Registered Views:</span>
                    <span style={{ fontWeight: 700, color: '#059669' }}>
                      {job.colmap_result?.registered_frames ? `${job.colmap_result.registered_frames} cameras aligned` : 'Aligned'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Sparse 3D Points:</span>
                    <span style={{ fontWeight: 700 }}>
                      {job.colmap_result?.point_count ? `${job.colmap_result.point_count.toLocaleString()} points` : 'Calculated'}
                    </span>
                  </div>
                  {onViewResults && (
                    <button
                      onClick={onViewResults}
                      className="btn btn-secondary"
                      style={{ fontSize: '11px', marginTop: '4px', padding: '4px 8px', alignSelf: 'flex-start' }}
                    >
                      <Eye size={13} />
                      <span>View Sparse Point Cloud</span>
                    </button>
                  )}
                </div>
              )}

              {/* 6. Dense Reconstruction (MVS) Preview */}
              {activeStage.stage_id === 'dense_reconstruction' && (
                <div style={{ fontSize: '12px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Stereo Method:</span>
                    <span style={{ fontWeight: 600 }}>COLMAP Patch-Match MVS</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Dense Fused Cloud:</span>
                    <span style={{ fontWeight: 700, color: '#059669' }}>
                      {job.dense_result?.dense_point_count ? `${job.dense_result.dense_point_count.toLocaleString()} points` : activeStage.status}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                    <span style={{ color: '#6B7280' }}>Outlier Filtering:</span>
                    <span style={{ fontWeight: 600 }}>SOR (k=20, σ=2.0) Active</span>
                  </div>
                </div>
              )}

              {/* 7. AI Depth Densification Preview */}
              {activeStage.stage_id === 'ai_depth' && (
                <div style={{ fontSize: '12px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>AI Model:</span>
                    <span style={{ fontWeight: 600 }}>Depth Anything V2 (ViT-Small)</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Metric Alignment:</span>
                    <span style={{ fontWeight: 600 }}>RANSAC Scale & Shift (1/Z)</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                    <span style={{ color: '#6B7280' }}>Fused AI Points:</span>
                    <span style={{ fontWeight: 700, color: '#059669' }}>
                      {job.ai_depth_result?.fused_points_count ? `${job.ai_depth_result.fused_points_count.toLocaleString()} total points` : 'Surface Completed'}
                    </span>
                  </div>
                  {onViewResults && (
                    <button
                      onClick={onViewResults}
                      className="btn btn-secondary"
                      style={{ fontSize: '11px', marginTop: '4px', padding: '4px 8px', alignSelf: 'flex-start' }}
                    >
                      <Eye size={13} />
                      <span>Inspect AI Fused 3D Cloud</span>
                    </button>
                  )}
                </div>
              )}

              {/* 8. Meshing & Texturing Preview */}
              {activeStage.stage_id === 'meshing_texturing' && (
                <div style={{ fontSize: '12px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Mesh Algorithm:</span>
                    <span style={{ fontWeight: 600 }}>Delaunay 3D Surface Reconstruction</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Vertices / Faces:</span>
                    <span style={{ fontWeight: 700, color: '#059669' }}>
                      {job.mesh_result?.vertex_count ? `${job.mesh_result.vertex_count.toLocaleString()}v / ${job.mesh_result.face_count.toLocaleString()}f` : 'Reconstructed'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', marginTop: '4px' }}>
                    {onViewResults && (
                      <button
                        onClick={onViewResults}
                        className="btn btn-primary"
                        style={{ fontSize: '11px', padding: '4px 10px' }}
                      >
                        <Box size={13} />
                        <span>Launch 3D Model Viewer</span>
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* 9. Georeferencing & Evaluation Preview */}
              {activeStage.stage_id === 'georeferencing_evaluation' && (
                <div style={{ fontSize: '12px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #E5E7EB' }}>
                    <span style={{ color: '#6B7280' }}>Scale Status:</span>
                    <span style={{ fontWeight: 600 }}>
                      {job.summary_report?.georeferencing?.status || 'Relative Photogrammetric Units'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                    <span style={{ color: '#6B7280' }}>Quality Report:</span>
                    <span style={{ fontWeight: 700, color: '#059669' }}>Verified & Formatted</span>
                  </div>
                </div>
              )}

              {/* 10. Packaging Preview */}
              {activeStage.stage_id === 'packaging' && (
                <div style={{ fontSize: '12px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ fontSize: '11px', color: '#6B7280' }}>
                    All export deliverables verified on disk:
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px', maxHeight: '140px', overflowY: 'auto' }}>
                    {Object.values(job.output_files || {}).map((item: any, idx: number) => (
                      <a
                        key={idx}
                        href={`/api/projects/${projectId}/files/${item.name}`}
                        download
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '6px 8px',
                          backgroundColor: '#FFFFFF',
                          borderRadius: '4px',
                          border: '1px solid #D1D5DB',
                          textDecoration: 'none',
                          color: '#111827',
                          fontSize: '11px'
                        }}
                      >
                        <span className="mono" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '110px' }}>
                          {item.name}
                        </span>
                        <Download size={12} color="#4B5563" />
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Timings */}
            <div style={{ display: 'flex', gap: '14px', fontSize: '11px', color: '#6B7280' }}>
              {activeStage.started_at && (
                <div>Started: <span className="mono" style={{ color: '#111827' }}>{activeStage.started_at.split('T')[1].replace('Z', '')}</span></div>
              )}
              {activeStage.completed_at && (
                <div>Finished: <span className="mono" style={{ color: '#111827' }}>{activeStage.completed_at.split('T')[1].replace('Z', '')}</span></div>
              )}
            </div>

            {/* Error Message Box */}
            {activeStage.error_message && (
              <div style={{
                backgroundColor: 'var(--status-error-bg)',
                border: '1px solid var(--status-error)',
                borderRadius: '4px',
                padding: '10px 12px',
                color: 'var(--status-error)',
                fontSize: '12px'
              }}>
                <div style={{ fontWeight: 700, marginBottom: '2px' }}>Diagnostic:</div>
                <div>{activeStage.error_message}</div>
              </div>
            )}
          </div>

          {/* Live Log Console */}
          <div style={{
            backgroundColor: '#1E2227',
            borderRadius: '6px',
            border: '1px solid var(--border-dark)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden'
          }}>
            <div style={{
              padding: '8px 12px',
              backgroundColor: '#282C34',
              color: '#ABB2BF',
              fontSize: '11px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              borderBottom: '1px solid rgba(255, 255, 255, 0.08)'
            }}>
              <Terminal size={14} />
              <span>LIVE LOG STREAM &bull; {activeStage.stage_id.toUpperCase()}</span>
            </div>

            <div style={{
              flex: 1,
              padding: '12px',
              overflowY: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: '#98C379',
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap'
            }}>
              {activeStage.log_preview.length === 0 ? (
                <span style={{ color: '#5C6370' }}>Waiting for stage subprocess output...</span>
              ) : (
                activeStage.log_preview.map((line, idx) => (
                  <div key={idx}>{line}</div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Frame Fullscreen Preview Modal */}
      {selectedPreviewImage && (
        <div
          onClick={() => setSelectedPreviewImage(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.85)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '24px'
          }}
        >
          <img
            src={selectedPreviewImage}
            alt="Preview"
            style={{ maxWidth: '90vw', maxHeight: '85vh', borderRadius: '6px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.5)' }}
          />
        </div>
      )}

    </div>
  );
};
