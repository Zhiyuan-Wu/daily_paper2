import {
  BookOutlined,
  DislikeOutlined,
  FileSearchOutlined,
  LikeOutlined,
  RobotOutlined,
  SnippetsOutlined,
} from '@ant-design/icons';
import { Button, Space, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { PaperRow } from '../api/types';

interface PaperTableProps {
  papers: PaperRow[];
  loading: boolean;
  total?: number;
  page?: number;
  pageSize?: number;
  onPageChange?: (page: number, pageSize: number) => void;
  onViewDetail?: (paper: PaperRow) => void;
  onReadOriginal?: (paper: PaperRow) => void;
  onAIInterpret?: (paper: PaperRow) => void;
  onAddNote?: (paper: PaperRow) => void;
  onToggleLike?: (paper: PaperRow) => void;
  onToggleDislike?: (paper: PaperRow) => void;
  aiSubmittingIds?: Set<string>;
  likeSubmittingIds?: Set<string>;
}

function formatPublishedAt(value: string | null): string {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function PaperTable({
  papers,
  loading,
  total,
  page,
  pageSize,
  onPageChange,
  onViewDetail,
  onReadOriginal,
  onAIInterpret,
  onAddNote,
  onToggleLike,
  onToggleDislike,
  aiSubmittingIds,
  likeSubmittingIds,
}: PaperTableProps) {
  const showActions = Boolean(
    onViewDetail || onReadOriginal || onAIInterpret || onAddNote || onToggleLike || onToggleDislike,
  );

  const columns: ColumnsType<PaperRow> = [
    ...(showActions
      ? [
          {
            title: '操作',
            key: 'actions',
            width: 300,
            fixed: 'left' as const,
            render: (_value: unknown, record: PaperRow) => {
              const targetUrl = record.pdf_url || record.online_url;
              const aiSubmitting = aiSubmittingIds?.has(record.id) ?? false;
              const likeSubmitting = likeSubmittingIds?.has(record.id) ?? false;

              return (
                <Space>
                  <Tooltip title="查看详情">
                    <Button
                      type="text"
                      icon={<FileSearchOutlined />}
                      onClick={() => onViewDetail?.(record)}
                    />
                  </Tooltip>

                  <Tooltip title={targetUrl ? '阅读原文' : '无可用链接'}>
                    <Button
                      type="text"
                      icon={<BookOutlined />}
                      disabled={!targetUrl}
                      onClick={() => onReadOriginal?.(record)}
                    />
                  </Tooltip>

                  <Tooltip title={aiSubmitting ? '任务提交中' : 'AI解读'}>
                    <Button
                      type="text"
                      icon={<RobotOutlined />}
                      loading={aiSubmitting}
                      onClick={() => onAIInterpret?.(record)}
                      disabled={aiSubmitting}
                    />
                  </Tooltip>

                  <Tooltip title="添加笔记">
                    <Button
                      type="text"
                      icon={<SnippetsOutlined />}
                      onClick={() => onAddNote?.(record)}
                    />
                  </Tooltip>

                  <Tooltip title={record.like === 1 ? '取消喜欢' : '标记喜欢'}>
                    <Button
                      aria-label="喜欢"
                      type={record.like === 1 ? 'primary' : 'text'}
                      icon={<LikeOutlined />}
                      loading={likeSubmitting}
                      disabled={likeSubmitting}
                      onClick={() => onToggleLike?.(record)}
                    />
                  </Tooltip>

                  <Tooltip title={record.like === -1 ? '取消不喜欢' : '标记不喜欢'}>
                    <Button
                      aria-label="不喜欢"
                      type={record.like === -1 ? 'primary' : 'text'}
                      danger={record.like === -1}
                      icon={<DislikeOutlined />}
                      loading={likeSubmitting}
                      disabled={likeSubmitting}
                      onClick={() => onToggleDislike?.(record)}
                    />
                  </Tooltip>
                </Space>
              );
            },
          },
        ]
      : []),
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 460,
      render: (value: string) => (
        <Typography.Text style={{ fontWeight: 600 }} ellipsis={{ tooltip: value }}>
          {value}
        </Typography.Text>
      ),
    },
    {
      title: '关键词',
      dataIndex: 'keywords',
      key: 'keywords',
      width: 260,
      render: (keywords: string[]) => renderTagList(keywords),
    },
    {
      title: '单位',
      dataIndex: 'affiliations',
      key: 'affiliations',
      width: 320,
      render: (affiliations: string[]) => renderTagList(affiliations),
    },
    {
      title: '发表时间',
      dataIndex: 'published_at',
      key: 'published_at',
      width: 190,
      render: (value: string | null) => formatPublishedAt(value),
    },
    {
      title: '论文源',
      dataIndex: 'source',
      key: 'source',
      width: 130,
    },
  ];

  return (
    <Table<PaperRow>
      rowKey={(record) => record.id}
      loading={loading}
      columns={columns}
      dataSource={papers}
      scroll={{ x: 1450 }}
      pagination={
        onPageChange && total !== undefined && page !== undefined && pageSize !== undefined
          ? {
              total,
              current: page,
              pageSize,
              showSizeChanger: true,
              pageSizeOptions: [10, 20, 50],
              onChange: onPageChange,
              showTotal: (value) => `共 ${value} 条`,
            }
          : false
      }
      locale={{ emptyText: '暂无论文数据' }}
    />
  );
}

function renderTagList(values: string[]) {
  if (values.length === 0) {
    return null;
  }
  return (
    <Space size={[4, 6]} wrap>
      {values.map((value) => (
        <Tag key={value}>{value}</Tag>
      ))}
    </Space>
  );
}
