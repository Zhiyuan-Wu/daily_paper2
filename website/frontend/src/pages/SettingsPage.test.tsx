import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SettingsPage } from './SettingsPage';

vi.mock('../api/client', () => ({
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
});
