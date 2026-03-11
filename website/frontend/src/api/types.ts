export interface PaperRow {
  id: string;
  title: string;
  authors: string[];
  keywords: string[];
  published_at: string | null;
  source: string;
  online_url: string;
  pdf_url: string;
  abstract: string;
  extra: Record<string, unknown>;
  local_pdf_path: string | null;
  local_text_path: string | null;
  recommendation_records: string[];
  user_notes: string;
  ai_report_summary: string;
  ai_report_path: string;
}

export interface ReportRecord {
  id: string;
  report_date: string;
  generated_at: string;
  related_paper_ids: string[];
  local_md_path: string;
}

export interface ExploreResponse {
  items: PaperRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface MarkdownResponse {
  report_id: string;
  local_md_path: string;
  content: string;
}

export interface ActivityRecord {
  id: string;
  recommendation_records: string[];
  user_notes: string;
  ai_report_summary: string;
  ai_report_path: string;
}

export interface TaskRecord {
  task_id: string;
  task_type: string;
  metadata: Record<string, unknown>;
  status: 'queued' | 'running' | 'success' | 'failed' | 'stopped';
  command: string[];
  log_path: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  running_seconds: number;
  pid: number | null;
  return_code: number | null;
  error: string | null;
}

export interface TaskLogChunk {
  task_id: string;
  offset: number;
  next_offset: number;
  content: string;
  completed: boolean;
}

export interface CreateTaskResponse {
  task_id: string;
  status: TaskRecord['status'];
  task: TaskRecord;
}
