import React from 'react';
import { ProjectSummary, CapabilitiesResponse } from '../../types';
import { Plus, Folder, Video, Layers, CheckCircle2, AlertCircle, HelpCircle, HardDrive } from 'lucide-react';

interface Props {
  projects: ProjectSummary[];
  activeProjectId: string | null;
  capabilities: CapabilitiesResponse | null;
  onSelectProject: (id: string) => void;
  onNewProject: () => void;
  onOpenCapabilities: () => void;
  onOpenExplore?: () => void;
}

export const Sidebar: React.FC<Props> = ({
  projects,
  activeProjectId,
  capabilities,
  onSelectProject,
  onNewProject,
  onOpenCapabilities,
  onOpenExplore,
}) => {
  return (
    <aside className="sidebar">
      {/* Brand Header */}
      <div style={{
        padding: '16px',
        borderBottom: '1px solid var(--border-dark)',
        display: 'flex',
        alignItems: 'center',
        gap: '10px'
      }}>
        <div style={{
          width: '32px',
          height: '32px',
          backgroundColor: 'var(--accent-lime)',
          borderRadius: '4px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#171A20'
        }}>
          <Layers size={20} strokeWidth={2.5} />
        </div>
        <div>
          <div style={{ fontSize: '15px', fontWeight: 800, letterSpacing: '-0.3px', color: '#F7F8FA' }}>
            BIRDS EYE
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-dark-subtle)' }}>
            3D Terrain Reconstruction
          </div>
        </div>
      </div>

      {/* Primary Action: New Reconstruction */}
      <div style={{ padding: '12px 16px' }}>
        <button
          onClick={onNewProject}
          className="btn btn-primary"
          style={{ width: '100%', padding: '10px 14px' }}
        >
          <Plus size={16} />
          <span>New Reconstruction</span>
        </button>
        {onOpenExplore && (
          <button
            onClick={onOpenExplore}
            className="btn btn-outline"
            style={{ width: '100%', padding: '10px 14px', marginTop: 8, color: '#F7F8FA', borderColor: 'rgba(167,237,121,0.5)' }}
            title="Demo: type any place and explore it in 3D with distance measuring"
          >
            <Layers size={16} />
            <span>Explore Any Place (Demo)</span>
          </button>
        )}
      </div>

      {/* Projects List Header */}
      <div style={{
        padding: '8px 16px 4px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '11px',
        fontWeight: 700,
        color: 'var(--text-dark-subtle)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px'
      }}>
        <span>Projects ({projects.length})</span>
      </div>

      {/* Projects List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 12px 8px' }}>
        {projects.length === 0 ? (
          <div style={{
            padding: '24px 12px',
            textAlign: 'center',
            color: 'var(--text-dark-subtle)',
            fontSize: '12px'
          }}>
            No projects yet. Click New Reconstruction to start.
          </div>
        ) : (
          projects.map((p) => {
            const isActive = p.id === activeProjectId;
            return (
              <div
                key={p.id}
                onClick={() => onSelectProject(p.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '9px 12px',
                  borderRadius: '4px',
                  marginBottom: '2px',
                  cursor: 'pointer',
                  backgroundColor: isActive ? 'var(--bg-sidebar-raised)' : 'transparent',
                  borderLeft: isActive ? '3px solid var(--accent-lime)' : '3px solid transparent',
                  transition: 'background-color 0.15s ease'
                }}
              >
                <Folder size={16} color={isActive ? 'var(--accent-lime)' : '#9298A1'} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: '13px',
                    fontWeight: isActive ? 600 : 500,
                    color: isActive ? '#F7F8FA' : '#C2C6CC',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis'
                  }}>
                    {p.name}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-dark-subtle)' }}>
                    {p.status === 'completed' ? 'Reconstructed' : p.video_uploaded ? 'Video ready' : 'No video'}
                  </div>
                </div>
                {p.has_results && (
                  <CheckCircle2 size={14} color="var(--accent-lime)" />
                )}
              </div>
            );
          })
        )}
      </div>

      {/* System Status Panel */}
      <div style={{
        padding: '12px 16px',
        backgroundColor: 'var(--bg-sidebar-raised)',
        borderTop: '1px solid var(--border-dark)',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px' }}>
          <span style={{ fontWeight: 700, color: 'var(--text-dark-subtle)', textTransform: 'uppercase' }}>
            Engine Diagnostics
          </span>
          <button
            onClick={onOpenCapabilities}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--accent-lime)',
              fontSize: '11px',
              cursor: 'pointer',
              fontWeight: 600
            }}
          >
            Details
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
          <span style={{ color: '#C2C6CC' }}>COLMAP SfM:</span>
          {capabilities?.colmap.available || capabilities?.sfm_engine === 'pycolmap' ? (
            <span style={{ color: 'var(--accent-lime)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={12} /> {capabilities?.colmap.available ? 'Ready' : 'Built-in engine'}
            </span>
          ) : (
            <span style={{ color: 'var(--status-error)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <AlertCircle size={12} /> Missing
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
          <span style={{ color: '#C2C6CC' }}>Disk Free:</span>
          <span className="mono" style={{ color: '#F7F8FA' }}>
            {capabilities?.disk_free_gb ?? '--'} GB
          </span>
        </div>
      </div>
    </aside>
  );
};
