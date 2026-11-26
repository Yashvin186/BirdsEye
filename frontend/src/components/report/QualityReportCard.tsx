import React from 'react';
import { Download, FileText, CheckCircle, AlertTriangle, Box, Camera, Layers } from 'lucide-react';

interface Props {
  projectId: string;
  qualityReport: any;
  files: Record<string, { filename: string; size_bytes: number; format: string; download_url: string }>;
}

export const QualityReportCard: React.FC<Props> = ({ projectId, qualityReport, files }) => {
  if (!qualityReport) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: '#606773' }}>
        Quality report will be generated upon completion of photogrammetry reconstruction.
      </div>
    );
  }

  const downloadFile = (url: string, filename: string) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
      
      {/* Metric Cards Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
        <div style={{ backgroundColor: '#F0F1F3', padding: '12px', borderRadius: '4px', border: '1px solid var(--border-light)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#606773', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase' }}>
            <Camera size={14} />
            <span>Registered Frames</span>
          </div>
          <div style={{ fontSize: '20px', fontWeight: 800, marginTop: '4px', color: '#171A20' }}>
            {qualityReport.sparse_sfm?.registered_frames} / {qualityReport.frame_extraction?.accepted_frames}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--accent-lime-dark)', fontWeight: 600 }}>
            {qualityReport.sparse_sfm?.registration_percentage}% registered
          </div>
        </div>

        <div style={{ backgroundColor: '#F0F1F3', padding: '12px', borderRadius: '4px', border: '1px solid var(--border-light)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#606773', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase' }}>
            <Layers size={14} />
            <span>Sparse 3D Points</span>
          </div>
          <div style={{ fontSize: '20px', fontWeight: 800, marginTop: '4px', color: '#171A20' }}>
            {qualityReport.sparse_sfm?.points_count?.toLocaleString()}
          </div>
          <div style={{ fontSize: '11px', color: '#606773' }}>
            COLMAP Triangulation
          </div>
        </div>

        <div style={{ backgroundColor: '#F0F1F3', padding: '12px', borderRadius: '4px', border: '1px solid var(--border-light)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#606773', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase' }}>
            <Box size={14} />
            <span>Dense / Mesh Surface</span>
          </div>
          <div style={{ fontSize: '20px', fontWeight: 800, marginTop: '4px', color: '#171A20' }}>
            {qualityReport.mesh?.vertex_count?.toLocaleString() || 0}
          </div>
          <div style={{ fontSize: '11px', color: '#606773' }}>
            {qualityReport.mesh?.face_count?.toLocaleString() || 0} Triangles
          </div>
        </div>

        <div style={{ backgroundColor: '#F0F1F3', padding: '12px', borderRadius: '4px', border: '1px solid var(--border-light)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#606773', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase' }}>
            <CheckCircle size={14} />
            <span>Georeference Scale</span>
          </div>
          <div style={{ fontSize: '13px', fontWeight: 700, marginTop: '6px', color: '#171A20', lineHeight: 1.2 }}>
            {qualityReport.georeferencing?.status}
          </div>
          <div style={{ fontSize: '10px', color: '#606773', marginTop: '2px' }}>
            Non-survey grade
          </div>
        </div>
      </div>

      {/* Georeferencing & Ground Truth Integrity */}
      <div style={{
        backgroundColor: '#F0F1F3',
        padding: '14px 16px',
        borderRadius: '4px',
        border: '1px solid var(--border-light)'
      }}>
        <h4 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', color: '#3D424B', marginBottom: '6px' }}>
          Georeferencing & Measurement Disclaimer
        </h4>
        <p style={{ fontSize: '12px', color: '#171A20', lineHeight: 1.5 }}>
          {qualityReport.georeferencing?.notes}
        </p>
      </div>

      {/* Available Output Downloads */}
      <div style={{
        backgroundColor: '#F0F1F3',
        padding: '14px 16px',
        borderRadius: '4px',
        border: '1px solid var(--border-light)'
      }}>
        <h4 style={{ fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', color: '#3D424B', marginBottom: '10px' }}>
          Verified Downloadable Outputs
        </h4>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
          {Object.entries(files).map(([key, file]) => (
            <div
              key={key}
              style={{
                backgroundColor: '#FFFFFF',
                padding: '10px 12px',
                borderRadius: '4px',
                border: '1px solid var(--border-light)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between'
              }}
            >
              <div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#171A20' }}>{file.filename}</div>
                <div style={{ fontSize: '11px', color: '#606773' }}>
                  {file.format} &bull; {(file.size_bytes / (1024 * 1024)).toFixed(2)} MB
                </div>
              </div>
              <button
                onClick={() => downloadFile(file.download_url, file.filename)}
                className="btn btn-outline"
                style={{ padding: '6px 8px', fontSize: '11px' }}
                title="Download file"
              >
                <Download size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Limitations List */}
      {qualityReport.limitations_and_disclaimers && (
        <div style={{
          backgroundColor: '#F3DDAA',
          border: '1px solid #946414',
          borderRadius: '4px',
          padding: '12px 14px',
          color: '#4A3408',
          fontSize: '12px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, marginBottom: '6px' }}>
            <AlertTriangle size={15} color="#946414" />
            <span>Reconstruction Limitations</span>
          </div>
          <ul style={{ paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
            {qualityReport.limitations_and_disclaimers.map((lim: string, idx: number) => (
              <li key={idx}>{lim}</li>
            ))}
          </ul>
        </div>
      )}

    </div>
  );
};
