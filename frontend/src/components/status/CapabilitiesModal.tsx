import React from 'react';
import { CapabilitiesResponse } from '../../types';
import { X, CheckCircle, AlertTriangle, XCircle, HardDrive, Cpu, Terminal, Camera } from 'lucide-react';

interface Props {
  capabilities: CapabilitiesResponse | null;
  onClose: () => void;
}

export const CapabilitiesModal: React.FC<Props> = ({ capabilities, onClose }) => {
  if (!capabilities) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.65)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      backdropFilter: 'blur(3px)'
    }}>
      <div style={{
        width: '680px',
        maxHeight: '85vh',
        backgroundColor: '#C7CAD1',
        borderRadius: '6px',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.35)',
        border: '1px solid var(--border-strong)',
        overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          backgroundColor: '#34383E',
          color: '#F7F8FA',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid var(--border-dark)'
        }}>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700 }}>System Readiness & Capabilities</h2>
            <p style={{ fontSize: '12px', color: '#C2C6CC', marginTop: '2px' }}>
              Detected environment parameters for local photogrammetry execution
            </p>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#F7F8FA', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          
          {/* Hardware & Environment Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '12px'
          }}>
            <div style={{ padding: '12px', backgroundColor: '#D7D9DE', borderRadius: '4px', border: '1px solid var(--border-light)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <Terminal size={16} color="#34383E" />
                <span style={{ fontSize: '12px', fontWeight: 700 }}>Host Platform & Python</span>
              </div>
              <div style={{ fontSize: '13px', fontWeight: 600 }}>{capabilities.os_name}</div>
              <div style={{ fontSize: '11px', color: '#3D424B', marginTop: '2px' }}>
                Python {capabilities.python_version}
              </div>
            </div>

            <div style={{ padding: '12px', backgroundColor: '#D7D9DE', borderRadius: '4px', border: '1px solid var(--border-light)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <HardDrive size={16} color="#34383E" />
                <span style={{ fontSize: '12px', fontWeight: 700 }}>Workspace Storage</span>
              </div>
              <div style={{ fontSize: '13px', fontWeight: 600 }}>{capabilities.disk_free_gb} GB Free</div>
              <div style={{ fontSize: '11px', color: '#3D424B', marginTop: '2px', wordBreak: 'break-all' }}>
                {capabilities.workspace_path}
              </div>
            </div>

            <div style={{ padding: '12px', backgroundColor: '#D7D9DE', borderRadius: '4px', border: '1px solid var(--border-light)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <Camera size={16} color="#34383E" />
                <span style={{ fontSize: '12px', fontWeight: 700 }}>COLMAP Engine</span>
                {capabilities.colmap.available ? (
                  <span className="badge badge-success" style={{ marginLeft: 'auto' }}>Available</span>
                ) : capabilities.sfm_engine === 'pycolmap' ? (
                  <span className="badge badge-warning" style={{ marginLeft: 'auto' }}>Built-in engine</span>
                ) : (
                  <span className="badge badge-error" style={{ marginLeft: 'auto' }}>Missing</span>
                )}
              </div>
              <div style={{ fontSize: '12px', fontWeight: 600 }}>
                {capabilities.colmap.version || (capabilities.sfm_engine === 'pycolmap' ? 'COLMAP program not found; using pycolmap' : 'Not detected on PATH')}
              </div>
              <div style={{ fontSize: '11px', color: '#3D424B', marginTop: '2px' }}>
                {capabilities.colmap.details}
              </div>
            </div>

            <div style={{ padding: '12px', backgroundColor: '#D7D9DE', borderRadius: '4px', border: '1px solid var(--border-light)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <Cpu size={16} color="#34383E" />
                <span style={{ fontSize: '12px', fontWeight: 700 }}>Graphics / CUDA</span>
                {capabilities.gpu.available ? (
                  <span className="badge badge-success" style={{ marginLeft: 'auto' }}>CUDA</span>
                ) : (
                  <span className="badge badge-warning" style={{ marginLeft: 'auto' }}>CPU Only</span>
                )}
              </div>
              <div style={{ fontSize: '11px', color: '#3D424B', marginTop: '2px' }}>
                {capabilities.gpu.details}
              </div>
            </div>
          </div>

          {/* Setup Recommendations */}
          {capabilities.setup_recommendations.length > 0 && (
            <div style={{
              padding: '12px 16px',
              backgroundColor: '#F3DDAA',
              border: '1px solid #946414',
              borderRadius: '4px',
              color: '#4A3408'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, fontSize: '13px', marginBottom: '4px' }}>
                <AlertTriangle size={15} color="#946414" />
                <span>Actionable Setup Recommendations</span>
              </div>
              <ul style={{ paddingLeft: '20px', fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {capabilities.setup_recommendations.map((rec, idx) => (
                  <li key={idx}>{rec}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Pipeline Stage Capabilities Table */}
          <div>
            <h4 style={{ fontSize: '13px', fontWeight: 700, marginBottom: '8px', color: '#171A20' }}>
              Pipeline Stages & Hardware Engine Support
            </h4>
            <div style={{
              backgroundColor: '#F0F1F3',
              borderRadius: '4px',
              border: '1px solid var(--border-light)',
              overflow: 'hidden'
            }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ backgroundColor: '#D7D9DE', borderBottom: '1px solid var(--border-light)', textAlign: 'left' }}>
                    <th style={{ padding: '8px 12px' }}>Stage</th>
                    <th style={{ padding: '8px 12px' }}>Status</th>
                    <th style={{ padding: '8px 12px' }}>Engine</th>
                    <th style={{ padding: '8px 12px' }}>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {capabilities.stages.map((st) => (
                    <tr key={st.stage_id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                      <td style={{ padding: '8px 12px', fontWeight: 600 }}>{st.title}</td>
                      <td style={{ padding: '8px 12px' }}>
                        {st.available ? (
                          <span style={{ color: 'var(--status-success)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                            <CheckCircle size={14} /> Ready
                          </span>
                        ) : (
                          <span style={{ color: 'var(--status-error)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                            <XCircle size={14} /> Blocked
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '8px 12px', color: '#3D424B' }}>{st.primary_engine}</td>
                      <td style={{ padding: '8px 12px', color: '#606773', fontSize: '11px' }}>{st.status_note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 20px',
          backgroundColor: '#AEB3BD',
          borderTop: '1px solid var(--border-light)',
          display: 'flex',
          justifyContent: 'flex-end'
        }}>
          <button className="btn btn-secondary" onClick={onClose}>
            Close Diagnostics
          </button>
        </div>
      </div>
    </div>
  );
};
