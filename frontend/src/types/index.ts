export interface DependencyInfo {
  name: string;
  available: boolean;
  version?: string;
  path?: string;
  details?: string;
}

export interface PipelineStageCapability {
  stage_id: string;
  title: string;
  available: boolean;
  primary_engine: string;
  status_note: string;
}

export interface CapabilitiesResponse {
  os_name: string;
  python_version: string;
  disk_free_gb: number;
  workspace_path: string;
  colmap: DependencyInfo;
  ffmpeg: DependencyInfo;
  opencv: DependencyInfo;
  gpu: DependencyInfo;
  mesh_tools: DependencyInfo;
  power_status?: {
    on_battery: boolean;
    charger_connected: boolean;
    battery_percent: number;
    status_text: string;
  };
  stages: PipelineStageCapability[];
  ready_for_pipeline: boolean;
  sfm_engine?: 'colmap' | 'pycolmap' | 'none';
  setup_recommendations: string[];
}

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  workspace_accessible: boolean;
  colmap_installed: boolean;
  ffmpeg_installed: boolean;
  gpu_available: boolean;
}

export interface VideoMetadata {
  filename: string;
  original_filename: string;
  size_bytes: number;
  duration_seconds: number;
  fps: number;
  frame_count: number;
  width: number;
  height: number;
  codec: string;
  aspect_ratio: string;
  has_audio: boolean;
  has_gps: boolean;
  gps_latitude?: number;
  gps_longitude?: number;
  gps_altitude?: number;
  warnings: string[];
}

export interface ProjectSummary {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  status: string;
  video_uploaded: boolean;
  video_metadata?: VideoMetadata;
  has_results: boolean;
  output_files_count: number;
}

export interface StageDetail {
  stage_id: string;
  title: string;
  status: 'pending' | 'running' | 'completed' | 'partial' | 'failed' | 'skipped' | 'unsupported';
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  progress_percent?: number;
  log_preview: string[];
  output_files: string[];
  warnings: string[];
  error_message?: string;
}

export interface PipelineConfigRequest {
  sampling_fps: number;
  max_frames: number;
  blur_threshold: number;
  similarity_threshold: number;
  matching_strategy: 'sequential' | 'exhaustive';
  gpu_mode?: 'auto' | 'cuda' | 'cpu';
  enable_dense_mvs: boolean;
  enable_ai_depth?: boolean;
  enable_meshing: boolean;
  enable_texturing?: boolean;
  quality_preset?: 'fast' | 'balanced' | 'high';
  fill_unseen_regions?: boolean;
  isolate_subject?: boolean;
  scene_mode?: 'auto' | 'aerial' | 'object';
  auto_shot_select?: boolean;
  cpu_stereo_fallback?: boolean;
}

export interface JobStatusResponse {
  job_id: string;
  project_id: string;
  status: 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';
  current_stage?: string;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  duration_seconds?: number;
  stages: StageDetail[];
  output_files: Record<string, { name: string; size_bytes: number; format: string }>;
  summary_report?: any;
  config?: any;
  colmap_result?: any;
  dense_result?: any;
  ai_depth_result?: any;
  mesh_result?: any;
  warnings: string[];
  error?: string;
}

export interface ProjectResultsResponse {
  project_id: string;
  files: Record<string, { filename: string; size_bytes: number; format: string; download_url: string }>;
  quality_report?: any;
  contact_sheet_url?: string;
}
