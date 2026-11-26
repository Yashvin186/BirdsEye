import React, { useState, useEffect } from 'react';
import {
  ProjectSummary,
  CapabilitiesResponse,
  VideoMetadata,
  PipelineConfigRequest,
  JobStatusResponse,
  ProjectResultsResponse,
} from './types';
import {
  fetchProjects,
  fetchCapabilities,
  createProject,
  startReconstruction,
  fetchJobStatus,
  cancelJob,
  fetchProjectResults,
  fetchProjectJob,
  deleteProject,
} from './api/client';
import { Sidebar } from './components/layout/Sidebar';
import { CapabilitiesModal } from './components/status/CapabilitiesModal';
import { VideoUploadCard } from './components/upload/VideoUploadCard';
import { PipelineView } from './components/pipeline/PipelineView';
import { ModelViewer } from './components/viewer/ModelViewer';
import { MapViewer } from './components/viewer/MapViewer';
import { ExploreDemo } from './components/viewer/ExploreDemo';
import { QualityReportCard } from './components/report/QualityReportCard';
import { ContactSheetModal } from './components/frames/ContactSheetModal';
import {
  Plus,
  Video,
  Layers,
  Box,
  FileText,
  Trash2,
  AlertCircle,
  RefreshCw,
  HardDrive,
  Cpu
} from 'lucide-react';

export const App: React.FC = () => {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);

  // Modals
  const [showCapabilitiesModal, setShowCapabilitiesModal] = useState(false);
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [showContactSheetModal, setShowContactSheetModal] = useState(false);

  // New Project Form
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [isCreatingProject, setIsCreatingProject] = useState(false);

  // Active Project Data
  const [activeTab, setActiveTab] = useState<'intake' | 'pipeline' | 'viewer' | 'map' | 'report'>('intake');
  const [exploreOpen, setExploreOpen] = useState(false);
  const [activeJob, setActiveJob] = useState<JobStatusResponse | null>(null);
  const [projectResults, setProjectResults] = useState<ProjectResultsResponse | null>(null);

  // Load initial environment & projects
  useEffect(() => {
    loadCapabilities();
    loadProjects();
  }, []);

  const loadCapabilities = async () => {
    try {
      const caps = await fetchCapabilities();
      setCapabilities(caps);
    } catch (err) {
      console.error('Failed to load capabilities:', err);
    }
  };

  const loadProjects = async () => {
    try {
      const list = await fetchProjects();
      setProjects(list);
      if (list.length > 0) {
        if (!activeProjectId || !list.some((p) => p.id === activeProjectId)) {
          setActiveProjectId(list[0].id);
        }
      } else {
        setActiveProjectId(null);
      }
    } catch (err) {
      console.error('Failed to load projects:', err);
    }
  };

  // Poll active project results & job status
  useEffect(() => {
    if (!activeProjectId) {
      setActiveJob(null);
      setProjectResults(null);
      return;
    }

    loadProjectData(activeProjectId);

    const interval = setInterval(() => {
      if (activeJob && (activeJob.status === 'running' || activeJob.status === 'queued')) {
        pollJob(activeJob.job_id);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeProjectId, activeJob?.status]);

  const loadProjectData = async (projId: string) => {
    try {
      const [results, job] = await Promise.all([
        fetchProjectResults(projId),
        fetchProjectJob(projId).catch(() => null),
      ]);
      setProjectResults(results);
      if (job) {
        setActiveJob(job);
      }

      // If project has output files, default to 3D Viewer tab if not already on pipeline
      if (Object.keys(results.files).length > 0 && activeTab === 'intake') {
        setActiveTab('viewer');
      }
    } catch (err) {
      console.error('Failed to load project results:', err);
      loadProjects();
    }
  };

  const pollJob = async (jobId: string) => {
    try {
      const status = await fetchJobStatus(jobId);
      const wasRunning = activeJob?.status === 'running' || activeJob?.status === 'queued';
      setActiveJob(status);
      if (status.status === 'completed' || status.status === 'partial') {
        if (activeProjectId) loadProjectData(activeProjectId);
        if (wasRunning) setActiveTab('viewer');   // finished -> show the result straight away
      }
    } catch (err) {
      console.error('Failed to poll job status:', err);
    }
  };

  const handleCreateProjectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    setIsCreatingProject(true);
    try {
      const created = await createProject(newProjectName.trim(), newProjectDesc.trim());
      setProjects([created, ...projects]);
      setActiveProjectId(created.id);
      setShowNewProjectModal(false);
      setNewProjectName('');
      setNewProjectDesc('');
      setActiveTab('intake');
    } catch (err: any) {
      alert(err.message || 'Failed to create project');
    } finally {
      setIsCreatingProject(false);
    }
  };

  const handleStartReconstruction = async (config: PipelineConfigRequest) => {
    if (!activeProjectId) return;
    try {
      const res = await startReconstruction(activeProjectId, config);
      setActiveTab('pipeline');
      const initialJob = await fetchJobStatus(res.job_id);
      setActiveJob(initialJob);
    } catch (err: any) {
      alert(err.message || 'Failed to start reconstruction');
    }
  };

  const handleCancelJob = async () => {
    if (!activeJob) return;
    try {
      await cancelJob(activeJob.job_id);
      const updated = await fetchJobStatus(activeJob.job_id);
      setActiveJob(updated);
    } catch (err: any) {
      alert(err.message || 'Failed to cancel job');
    }
  };

  const handleDeleteActiveProject = async () => {
    if (!activeProjectId) return;
    if (!confirm('Are you sure you want to permanently delete this project and all reconstructed files?')) return;

    try {
      await deleteProject(activeProjectId);
      const remaining = projects.filter((p) => p.id !== activeProjectId);
      setProjects(remaining);
      setActiveProjectId(remaining.length > 0 ? remaining[0].id : null);
    } catch (err: any) {
      alert(err.message || 'Failed to delete project');
    }
  };

  const activeProject = projects.find((p) => p.id === activeProjectId);

  return (
    <div className="app-shell">
      {/* Sidebar Navigation */}
      <Sidebar
        projects={projects}
        activeProjectId={activeProjectId}
        capabilities={capabilities}
        onSelectProject={(id) => {
          setActiveProjectId(id);
          setActiveTab('intake');
        }}
        onNewProject={() => setShowNewProjectModal(true)}
        onOpenCapabilities={() => setShowCapabilitiesModal(true)}
        onOpenExplore={() => setExploreOpen(true)}
      />

      {/* Main Working Surface */}
      <main className="main-content">
        {exploreOpen ? (
          <ExploreDemo onClose={() => setExploreOpen(false)} />
        ) : activeProject ? (
          <>
            {/* Project Header */}
            <header style={{
              padding: '14px 20px',
              backgroundColor: '#D7D9DE',
              borderBottom: '1px solid var(--border-light)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h1 style={{ fontSize: '18px', fontWeight: 800, color: '#171A20' }}>
                    {activeProject.name}
                  </h1>
                  <span className="mono" style={{ fontSize: '11px', color: '#606773' }}>
                    ({activeProject.id})
                  </span>
                </div>
                {activeProject.description && (
                  <p style={{ fontSize: '12px', color: '#3D424B', marginTop: '2px' }}>
                    {activeProject.description}
                  </p>
                )}
              </div>

              {/* Navigation Tabs */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <button
                  onClick={() => setActiveTab('intake')}
                  className={`btn ${activeTab === 'intake' ? 'btn-primary' : 'btn-outline'}`}
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                >
                  <Video size={14} />
                  <span>1 · Upload Video</span>
                </button>

                <button
                  onClick={() => setActiveTab('pipeline')}
                  className={`btn ${activeTab === 'pipeline' ? 'btn-primary' : 'btn-outline'}`}
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                >
                  <Layers size={14} />
                  <span>2 · Processing</span>
                  {activeJob?.status === 'running' && (
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#435B8A' }} />
                  )}
                </button>

                <button
                  onClick={() => setActiveTab('viewer')}
                  disabled={!projectResults || Object.keys(projectResults.files).length === 0}
                  className={`btn ${activeTab === 'viewer' ? 'btn-primary' : 'btn-outline'}`}
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                >
                  <Box size={14} />
                  <span>3 · 3D Model &amp; Measure</span>
                </button>

                <button
                  onClick={() => setActiveTab('map')}
                  disabled={!projectResults?.files?.['orthomosaic.jpg']}
                  title={projectResults?.files?.['orthomosaic.jpg'] ? 'Top-down map with measuring' : 'Available for straight-down survey flights'}
                  className={`btn ${activeTab === 'map' ? 'btn-primary' : 'btn-outline'}`}
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                >
                  <Box size={14} />
                  <span>4 · Map</span>
                </button>

                <button
                  onClick={() => setActiveTab('report')}
                  disabled={!projectResults?.quality_report}
                  className={`btn ${activeTab === 'report' ? 'btn-primary' : 'btn-outline'}`}
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                >
                  <FileText size={14} />
                  <span>5 · Report &amp; Download</span>
                </button>

                <button
                  onClick={handleDeleteActiveProject}
                  title="Delete Project"
                  className="btn btn-outline"
                  style={{ padding: '6px 8px', color: 'var(--status-error)', borderColor: 'rgba(168, 50, 61, 0.4)' }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </header>

            {/* Viewport Content */}
            <div style={{ flex: 1, padding: (activeTab === 'viewer' || activeTab === 'map') ? 0 : '16px', overflowY: (activeTab === 'viewer' || activeTab === 'map') ? 'hidden' : 'auto', position: 'relative' }}>
              {activeTab === 'intake' && (
                <VideoUploadCard
                  projectId={activeProject.id}
                  existingMetadata={activeProject.video_metadata || null}
                  capabilities={capabilities}
                  onVideoUploaded={(meta) => {
                    activeProject.video_metadata = meta;
                    activeProject.video_uploaded = true;
                    setProjects([...projects]);
                  }}
                  onStartReconstruction={handleStartReconstruction}
                  isProcessing={activeJob?.status === 'running'}
                />
              )}

              {activeTab === 'pipeline' && (
                <PipelineView
                  job={activeJob}
                  onCancelJob={handleCancelJob}
                  onViewContactSheet={() => setShowContactSheetModal(true)}
                  onViewResults={() => setActiveTab('viewer')}
                />
              )}

              {activeTab === 'viewer' && projectResults && (
                <ModelViewer
                  projectId={activeProject.id}
                  files={projectResults.files}
                  qualityReport={projectResults.quality_report}
                />
              )}

              {activeTab === 'map' && projectResults && (
                <MapViewer files={projectResults.files} qualityReport={projectResults.quality_report} />
              )}

              {activeTab === 'report' && projectResults && (
                <QualityReportCard
                  projectId={activeProject.id}
                  qualityReport={projectResults.quality_report}
                  files={projectResults.files}
                />
              )}
            </div>
          </>
        ) : (
          /* Empty State */
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '16px',
            color: '#3D424B'
          }}>
            <div style={{
              width: '56px',
              height: '56px',
              backgroundColor: '#D7D9DE',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Layers size={28} color="#606773" />
            </div>
            <div style={{ textAlign: 'center' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#171A20' }}>
                Welcome to Birds Eye
              </h2>
              <p style={{ fontSize: '13px', color: '#606773', maxWidth: '380px', marginTop: '4px' }}>
                Reconstruct 3D terrain and site models from single-pass continuous drone footage using photogrammetry.
              </p>
            </div>
            <button onClick={() => setShowNewProjectModal(true)} className="btn btn-primary" style={{ padding: '10px 18px' }}>
              <Plus size={16} />
              <span>Create First Project</span>
            </button>
          </div>
        )}
      </main>

      {/* New Project Modal */}
      {showNewProjectModal && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.65)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            width: '460px',
            backgroundColor: '#C7CAD1',
            borderRadius: '6px',
            padding: '20px',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.35)',
            border: '1px solid var(--border-strong)'
          }}>
            <h2 style={{ fontSize: '16px', fontWeight: 800, color: '#171A20', marginBottom: '14px' }}>
              Create New Reconstruction Project
            </h2>
            <form onSubmit={handleCreateProjectSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', display: 'block', marginBottom: '4px' }}>
                  Project Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Quarry North Flyover"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '4px', border: '1px solid var(--border-strong)', fontSize: '13px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, color: '#171A20', display: 'block', marginBottom: '4px' }}>
                  Site Description (Optional)
                </label>
                <textarea
                  rows={3}
                  placeholder="e.g. Continuous single pass at 60m AGL, overcast conditions"
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '4px', border: '1px solid var(--border-strong)', fontSize: '13px', resize: 'none' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
                <button type="button" onClick={() => setShowNewProjectModal(false)} className="btn btn-outline">
                  Cancel
                </button>
                <button type="submit" disabled={isCreatingProject} className="btn btn-primary">
                  {isCreatingProject ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* System Capabilities Modal */}
      {showCapabilitiesModal && (
        <CapabilitiesModal
          capabilities={capabilities}
          onClose={() => setShowCapabilitiesModal(false)}
        />
      )}

      {/* Keyframe Contact Sheet Modal */}
      {showContactSheetModal && projectResults?.contact_sheet_url && (
        <ContactSheetModal
          contactSheetUrl={projectResults.contact_sheet_url}
          onClose={() => setShowContactSheetModal(false)}
        />
      )}
    </div>
  );
};
