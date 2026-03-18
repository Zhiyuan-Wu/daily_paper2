import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SettingsPage } from './SettingsPage';

vi.mock('../api/client', () => ({
  createDocsQuestionTask: vi.fn(async () => ({
    task_id: 'docs-task-1',
    status: 'queued',
    task: {
      task_id: 'docs-task-1',
      task_type: 'docs_question',
      metadata: {},
      status: 'queued',
      command: [],
      log_path: '',
      created_at: '',
      started_at: null,
      finished_at: null,
      running_seconds: 0,
      pid: null,
      return_code: null,
      error: null,
    },
  })),
  getTasks: vi.fn(async () => []),
  stopTask: vi.fn(async () => ({ task: null })),
  getTaskLogs: vi.fn(async () => ({
    task_id: 't1',
    offset: 0,
    next_offset: 0,
    content: '',
    completed: false,
  })),
}));

describe('SettingsPage', () => {
  it('shows empty state when no running tasks', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('当前没有运行任务')).toBeInTheDocument();
    });
  });

  it('opens docs question modal and submits a task', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await user.click(screen.getAllByRole('button', { name: '提问 Claude' })[0]);
    expect(screen.getByRole('dialog', { name: '提问 Claude' })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('请输入你的问题'), '如何使用 CLI 获取论文？');
    await user.click(screen.getByRole('button', { name: /发\s*送/ }));

    await waitFor(() => {
      expect(screen.getByText('任务日志 - docs-task-1')).toBeInTheDocument();
    });
  });
});
