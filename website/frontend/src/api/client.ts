import type {
  ActivityRecord,
  CreateTaskResponse,
  ExploreResponse,
  MarkdownResponse,
  PaperMarkdownResponse,
  PaperRow,
  ReportRecord,
  TaskLogChunk,
  TaskRecord,
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      // fallback to status text
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export function getReportByDate(reportDate: string): Promise<ReportRecord> {
  return request<ReportRecord>(`/api/reports/by-date?date=${encodeURIComponent(reportDate)}`);
}

export function getReportPapers(reportId: string): Promise<PaperRow[]> {
  return request<PaperRow[]>(`/api/reports/${encodeURIComponent(reportId)}/papers`);
}

export function getReportMarkdown(reportId: string): Promise<MarkdownResponse> {
  return request<MarkdownResponse>(`/api/reports/${encodeURIComponent(reportId)}/markdown`);
}

export function getPaperAiInterpretMarkdown(paperId: string): Promise<PaperMarkdownResponse> {
  return request<PaperMarkdownResponse>(
    `/api/papers/${encodeURIComponent(paperId)}/ai-interpret-markdown`,
  );
}

export function generateReport(reportDate: string): Promise<CreateTaskResponse> {
  return request<CreateTaskResponse>('/api/reports/generate', {
    method: 'POST',
    body: JSON.stringify({ report_date: reportDate }),
  });
}

export function getExplorePapers(params: {
  page: number;
  pageSize: number;
  keyword?: string;
  source?: string;
}): Promise<ExploreResponse> {
  const query = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
    keyword: params.keyword ?? '',
    source: params.source ?? '',
  });
  return request<ExploreResponse>(`/api/papers/explore?${query.toString()}`);
}

export function getPaperDetail(paperId: string): Promise<PaperRow> {
  return request<PaperRow>(`/api/papers/${encodeURIComponent(paperId)}/detail`);
}

export function updatePaperNotes(paperId: string, userNotes: string): Promise<ActivityRecord> {
  return request<ActivityRecord>(`/api/activities/${encodeURIComponent(paperId)}/notes`, {
    method: 'PATCH',
    body: JSON.stringify({ user_notes: userNotes }),
  });
}

export function updatePaperLike(paperId: string, like: -1 | 0 | 1): Promise<ActivityRecord> {
  return request<ActivityRecord>(`/api/activities/${encodeURIComponent(paperId)}/like`, {
    method: 'PATCH',
    body: JSON.stringify({ like }),
  });
}

export function createAiInterpretTask(paperId: string): Promise<CreateTaskResponse> {
  return request<CreateTaskResponse>(`/api/papers/${encodeURIComponent(paperId)}/ai-interpret`, {
    method: 'POST',
  });
}

export function getTasks(status?: string): Promise<TaskRecord[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  return request<TaskRecord[]>(`/api/tasks${query}`);
}

export function stopTask(taskId: string): Promise<{ task: TaskRecord }> {
  return request<{ task: TaskRecord }>(`/api/tasks/${encodeURIComponent(taskId)}/stop`, {
    method: 'POST',
  });
}

export function getTaskLogs(taskId: string, offset: number): Promise<TaskLogChunk> {
  const query = new URLSearchParams({ offset: String(offset) });
  return request<TaskLogChunk>(`/api/tasks/${encodeURIComponent(taskId)}/logs?${query.toString()}`);
}
