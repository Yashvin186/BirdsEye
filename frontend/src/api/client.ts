import {
  HealthResponse,
  CapabilitiesResponse,
  ProjectSummary,
  VideoMetadata,
  PipelineConfigRequest,
  JobStatusResponse,
  ProjectResultsResponse,
} from '../types';

const BASE_URL = '';

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE_URL}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function fetchCapabilities(): Promise<CapabilitiesResponse> {
  const res = await fetch(`${BASE_URL}/api/capabilities`);
  if (!res.ok) throw new Error(`Failed to fetch capabilities: ${res.statusText}`);
  return res.json();
}

export async function fetchProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${BASE_URL}/api/projects`);
  if (!res.ok) throw new Error(`Failed to fetch projects: ${res.statusText}`);
  return res.json();
}

export async function createProject(name: string, description?: string): Promise<ProjectSummary> {
  const res = await fetch(`${BASE_URL}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create project');
  }
  return res.json();
}

export async function uploadVideo(projectId: string, file: File): Promise<VideoMetadata> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/video`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to upload video');
  }
  return res.json();
}

export async function uploadTelemetry(projectId: string, file: File): Promise<{ filename: string; samples: number; duration_s: number; start: { lat: number; lon: number } }> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/telemetry`, { method: 'POST', body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to upload flight log');
  }
  return res.json();
}

export async function importImageFolder(projectId: string, path: string, maxImages: number): Promise<VideoMetadata> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/import_folder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, max_images: maxImages }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to import the image folder');
  }
  return res.json();
}

export async function startReconstruction(projectId: string, config: PipelineConfigRequest): Promise<{ job_id: string }> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/reconstruction`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to start reconstruction');
  }
  return res.json();
}

export async function fetchJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Failed to fetch job status: ${res.statusText}`);
  return res.json();
}

export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to cancel job');
}

export async function fetchProjectResults(projectId: string): Promise<ProjectResultsResponse> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/results`);
  if (!res.ok) throw new Error('Failed to fetch project results');
  return res.json();
}

export async function fetchProjectFrames(projectId: string): Promise<{ frames: { filename: string; url: string }[]; total_count: number }> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/frames`);
  if (!res.ok) return { frames: [], total_count: 0 };
  return res.json();
}

export async function fetchProjectJob(projectId: string): Promise<JobStatusResponse | null> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/job`);
  if (!res.ok) return null;
  return res.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete project');
}

export async function fetchSampleVideos(): Promise<Array<{ name: string; size_mb: number }>> {
  const res = await fetch(`${BASE_URL}/api/projects/samples/list`);
  if (!res.ok) return [];
  return res.json();
}

export async function loadSampleVideo(projectId: string, sampleName: string = 'some.mp4'): Promise<VideoMetadata> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/load_sample?sample_name=${encodeURIComponent(sampleName)}`, {
    method: 'POST'
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to load sample video');
  }
  return res.json();
}

