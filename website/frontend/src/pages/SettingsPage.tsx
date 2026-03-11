import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Empty,
  Modal,
  Segmented,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useRef, useState } from 'react';

import { getTaskLogs, getTasks, stopTask } from '../api/client';
import type { TaskRecord } from '../api/types';

const STATUS_COLOR: Record<TaskRecord['status'], string> = {
  queued: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  stopped: 'warning',
};

function formatTime(value: string | null): string {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return '-';
  }
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const mins = Math.floor(seconds / 60);
  const remain = Math.floor(seconds % 60);
  return `${mins}m ${remain}s`;
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [messageApi, contextHolder] = message.useMessage();

  const [taskFilter, setTaskFilter] = useState<'running' | 'all'>('running');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const [logText, setLogText] = useState('');
  const [logOffset, setLogOffset] = useState(0);
  const [logError, setLogError] = useState<string | null>(null);
  const [logCompleted, setLogCompleted] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const [autoScroll, setAutoScroll] = useState(true);

  const logContainerRef = useRef<HTMLPreElement | null>(null);

  const tasksQuery = useQuery({
    queryKey: ['tasks', taskFilter],
    queryFn: () => getTasks(taskFilter === 'running' ? 'running' : undefined),
    refetchInterval: 2_000,
  });

  const stopMutation = useMutation({
    mutationFn: (taskId: string) => stopTask(taskId),
    onSuccess: () => {
      messageApi.success('任务已停止');
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (error: Error) => {
      messageApi.error(`停止任务失败: ${error.message}`);
    },
  });

  const columns: ColumnsType<TaskRecord> = useMemo(
    () => [
      {
        title: '任务ID',
        dataIndex: 'task_id',
        key: 'task_id',
        width: 180,
      },
      {
        title: '任务类型',
        dataIndex: 'task_type',
        key: 'task_type',
        width: 160,
      },
      {
        title: '关联信息',
        key: 'metadata',
        render: (_, task) => {
          const entries = Object.entries(task.metadata ?? {});
          if (entries.length === 0) {
            return '-';
          }
          return entries
            .slice(0, 2)
            .map(([key, value]) => `${key}: ${String(value)}`)
            .join(' | ');
        },
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 120,
        render: (status: TaskRecord['status']) => <Tag color={STATUS_COLOR[status]}>{status}</Tag>,
      },
      {
        title: '启动时间',
        dataIndex: 'started_at',
        key: 'started_at',
        width: 200,
        render: (value: string | null) => formatTime(value),
      },
      {
        title: '运行时长',
        dataIndex: 'running_seconds',
        key: 'running_seconds',
        width: 130,
        render: (value: number) => formatDuration(value),
      },
      {
        title: '操作',
        key: 'actions',
        width: 110,
        render: (_, task) => (
          <Button
            size="small"
            disabled={task.status !== 'running' && task.status !== 'queued'}
            loading={stopMutation.isPending}
            onClick={(event) => {
              event.stopPropagation();
              stopMutation.mutate(task.task_id);
            }}
          >
            停止
          </Button>
        ),
      },
    ],
    [stopMutation],
  );

  useEffect(() => {
    if (!selectedTaskId) {
      return;
    }

    let timer: number | null = null;
    let cancelled = false;

    const fetchLogs = async () => {
      try {
        const chunk = await getTaskLogs(selectedTaskId, logOffset);
        if (cancelled) {
          return;
        }

        setLogText((current) => (chunk.content ? `${current}${chunk.content}` : current));
        setLogOffset(chunk.next_offset);
        setLogCompleted(chunk.completed);
        setLastUpdated(new Date().toLocaleTimeString());
        setLogError(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setLogError((error as Error).message);
      }
    };

    void fetchLogs();
    timer = window.setInterval(() => {
      void fetchLogs();
    }, 1_500);

    return () => {
      cancelled = true;
      if (timer !== null) {
        window.clearInterval(timer);
      }
    };
  }, [selectedTaskId, logOffset]);

  useEffect(() => {
    if (!autoScroll || !logContainerRef.current) {
      return;
    }

    logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
  }, [autoScroll, logText]);

  const tasks = tasksQuery.data ?? [];

  return (
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
      {contextHolder}
      <Typography.Title level={3} style={{ margin: 0 }}>
        设置
      </Typography.Title>

      <Card>
        <Space style={{ marginBottom: 12 }} wrap>
          <Segmented
            value={taskFilter}
            onChange={(value) => setTaskFilter(value as 'running' | 'all')}
            options={[
              { label: '运行中', value: 'running' },
              { label: '全部', value: 'all' },
            ]}
          />
        </Space>

        {tasksQuery.error ? (
          <Alert
            type="error"
            showIcon
            message="任务加载失败"
            description={(tasksQuery.error as Error).message}
          />
        ) : null}

        {tasks.length === 0 && !tasksQuery.isLoading ? (
          <Empty description={taskFilter === 'running' ? '当前没有运行任务' : '暂无任务'} />
        ) : (
          <Table<TaskRecord>
            rowKey={(record) => record.task_id}
            loading={tasksQuery.isLoading}
            columns={columns}
            dataSource={tasks}
            scroll={{ x: 1080 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            onRow={(record) => ({
              onClick: () => {
                setSelectedTaskId(record.task_id);
                setLogText('');
                setLogOffset(0);
                setLogCompleted(false);
                setLogError(null);
                setLastUpdated('');
              },
            })}
          />
        )}
      </Card>

      <Modal
        title={selectedTaskId ? `任务日志 - ${selectedTaskId}` : '任务日志'}
        open={Boolean(selectedTaskId)}
        onCancel={() => setSelectedTaskId(null)}
        footer={null}
        width={920}
      >
        <Space style={{ marginBottom: 8 }}>
          <Typography.Text>自动滚动</Typography.Text>
          <Switch checked={autoScroll} onChange={setAutoScroll} />
          <Typography.Text type="secondary">最后更新: {lastUpdated || '-'}</Typography.Text>
          {logCompleted ? <Tag color="success">任务已结束</Tag> : null}
        </Space>

        {logError ? <Alert type="error" showIcon message="日志加载失败" description={logError} /> : null}

        {!logText && !logError ? <Empty description="暂无日志输出" /> : null}

        <pre
          ref={logContainerRef}
          style={{
            marginTop: 12,
            padding: 12,
            minHeight: 280,
            maxHeight: 460,
            overflow: 'auto',
            fontFamily: 'IBM Plex Mono, ui-monospace, monospace',
            background: '#0f172a',
            color: '#e2e8f0',
            borderRadius: 10,
            whiteSpace: 'pre-wrap',
          }}
        >
          {logText}
        </pre>
      </Modal>
    </Space>
  );
}
