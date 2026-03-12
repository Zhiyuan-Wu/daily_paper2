import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  Modal,
  Space,
  Spin,
  Typography,
  message,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useMemo, useState } from 'react';

import {
  ApiError,
  createAiInterpretTask,
  generateReport,
  getPaperDetail,
  getPaperAiInterpretMarkdown,
  getReportByDate,
  getReportMarkdown,
  getReportPapers,
  updatePaperLike,
  updatePaperNotes,
} from '../api/client';
import type { PaperRow } from '../api/types';
import { MarkdownViewer } from '../components/MarkdownViewer';
import { PaperTable } from '../components/PaperTable';

const TODAY = dayjs();

function likeLabel(value: -1 | 0 | 1): string {
  if (value === 1) {
    return '喜欢';
  }
  if (value === -1) {
    return '不喜欢';
  }
  return '无信息';
}

export function DailyReportPage() {
  const queryClient = useQueryClient();
  const [messageApi, contextHolder] = message.useMessage();

  const [pickedDate, setPickedDate] = useState<Dayjs>(TODAY);
  const [queryDate, setQueryDate] = useState<string>(TODAY.format('YYYY-MM-DD'));

  const [detailPaperId, setDetailPaperId] = useState<string | null>(null);
  const [notePaper, setNotePaper] = useState<PaperRow | null>(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [aiMarkdownPaper, setAiMarkdownPaper] = useState<PaperRow | null>(null);
  const [aiMarkdownPath, setAiMarkdownPath] = useState('');
  const [aiMarkdownContent, setAiMarkdownContent] = useState('');
  const [aiSubmittingIds, setAiSubmittingIds] = useState<Set<string>>(new Set());
  const [likeSubmittingIds, setLikeSubmittingIds] = useState<Set<string>>(new Set());

  const reportQuery = useQuery({
    queryKey: ['report-by-date', queryDate],
    queryFn: () => getReportByDate(queryDate),
    retry: false,
  });

  const report = reportQuery.data;

  const reportPapersQuery = useQuery({
    queryKey: ['report-papers', report?.id],
    queryFn: () => getReportPapers(report?.id ?? ''),
    enabled: Boolean(report?.id),
  });

  const reportMarkdownQuery = useQuery({
    queryKey: ['report-markdown', report?.id],
    queryFn: () => getReportMarkdown(report?.id ?? ''),
    enabled: Boolean(report?.id),
    retry: false,
  });

  const detailQuery = useQuery({
    queryKey: ['daily-detail', detailPaperId],
    queryFn: () => getPaperDetail(detailPaperId ?? ''),
    enabled: Boolean(detailPaperId),
  });

  const noteMutation = useMutation({
    mutationFn: ({ paperId, userNotes }: { paperId: string; userNotes: string }) =>
      updatePaperNotes(paperId, userNotes),
    onSuccess: () => {
      if (report?.id) {
        void queryClient.invalidateQueries({ queryKey: ['report-papers', report.id] });
      }
      if (detailPaperId) {
        void queryClient.invalidateQueries({ queryKey: ['daily-detail', detailPaperId] });
      }
      messageApi.success('笔记已保存');
      setNotePaper(null);
    },
    onError: (error: Error) => {
      messageApi.error(`笔记保存失败: ${error.message}`);
    },
  });

  const aiMutation = useMutation({
    mutationFn: (paperId: string) => createAiInterpretTask(paperId),
    onSuccess: (payload, paperId) => {
      setAiSubmittingIds((current) => {
        const next = new Set(current);
        next.delete(paperId);
        return next;
      });
      messageApi.success(`AI解读任务已提交: ${payload.task_id}`);
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (error: Error, paperId) => {
      setAiSubmittingIds((current) => {
        const next = new Set(current);
        next.delete(paperId);
        return next;
      });
      messageApi.error(`AI解读提交失败: ${error.message}`);
    },
  });

  const likeMutation = useMutation({
    mutationFn: ({ paperId, like }: { paperId: string; like: -1 | 0 | 1 }) =>
      updatePaperLike(paperId, like),
    onSuccess: (_payload, variables) => {
      setLikeSubmittingIds((current) => {
        const next = new Set(current);
        next.delete(variables.paperId);
        return next;
      });
      if (report?.id) {
        void queryClient.invalidateQueries({ queryKey: ['report-papers', report.id] });
      }
      if (detailPaperId) {
        void queryClient.invalidateQueries({ queryKey: ['daily-detail', detailPaperId] });
      }
      messageApi.success(`偏好已更新为: ${likeLabel(variables.like)}`);
    },
    onError: (error: Error, variables) => {
      setLikeSubmittingIds((current) => {
        const next = new Set(current);
        next.delete(variables.paperId);
        return next;
      });
      messageApi.error(`偏好更新失败: ${error.message}`);
    },
  });

  const generateMutation = useMutation({
    mutationFn: (reportDate: string) => generateReport(reportDate),
    onSuccess: (payload) => {
      messageApi.success(`日报生成任务已创建: ${payload.task_id}`);
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (error: Error) => {
      messageApi.error(`创建日报任务失败: ${error.message}`);
    },
  });

  const reportNotFound = reportQuery.error instanceof ApiError && reportQuery.error.status === 404;

  const markdownUnavailable =
    reportMarkdownQuery.error instanceof ApiError && reportMarkdownQuery.error.status === 404;

  const detailPaper = detailQuery.data;
  const detailCards = useMemo(() => {
    if (!detailPaper) {
      return null;
    }

    return (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card title="论文信息" size="small">
          <p>
            <strong>ID:</strong> {detailPaper.id}
          </p>
          <p>
            <strong>标题:</strong> {detailPaper.title}
          </p>
          <p>
            <strong>作者:</strong> {detailPaper.authors.join(', ') || '-'}
          </p>
          <p>
            <strong>摘要:</strong> {detailPaper.abstract || '-'}
          </p>
          <p>
            <strong>来源:</strong> {detailPaper.source}
          </p>
          <p>
            <strong>发表时间:</strong> {detailPaper.published_at || '-'}
          </p>
          <p>
            <strong>在线链接:</strong> {detailPaper.online_url || '-'}
          </p>
          <p>
            <strong>PDF链接:</strong> {detailPaper.pdf_url || '-'}
          </p>
        </Card>

        <Card title="活动信息" size="small">
          <p>
            <strong>推荐记录:</strong>{' '}
            {detailPaper.recommendation_records.length > 0
              ? detailPaper.recommendation_records.join(', ')
              : '-'}
          </p>
          <p>
            <strong>用户笔记:</strong> {detailPaper.user_notes || '-'}
          </p>
          <p>
            <strong>偏好:</strong> {likeLabel(detailPaper.like)}
          </p>
          <p>
            <strong>AI摘要:</strong> {detailPaper.ai_report_summary || '-'}
          </p>
          <p>
            <strong>AI报告路径:</strong> {detailPaper.ai_report_path || '-'}
          </p>
        </Card>
      </Space>
    );
  }, [detailPaper]);

  return (
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
      {contextHolder}
      <Typography.Title level={3} style={{ margin: 0 }}>
        论文日报
      </Typography.Title>

      <Card>
        <Space align="end" wrap>
          <div>
            <Typography.Text>选择日期</Typography.Text>
            <DatePicker
              value={pickedDate}
              onChange={(value) => setPickedDate(value ?? TODAY)}
              style={{ display: 'block', marginTop: 8 }}
            />
          </div>
          <Button
            type="primary"
            onClick={() => setQueryDate(pickedDate.format('YYYY-MM-DD'))}
            loading={reportQuery.isLoading}
          >
            查询
          </Button>
        </Space>
      </Card>

      {reportQuery.error && !reportNotFound ? (
        <Alert
          type="error"
          showIcon
          message="日报查询失败"
          description={(reportQuery.error as Error).message}
        />
      ) : null}

      {reportNotFound ? (
        <Card>
          <Empty description="该日期暂无日报">
            <Button
              type="primary"
              onClick={() => generateMutation.mutate(queryDate)}
              loading={generateMutation.isPending}
            >
              生成日报
            </Button>
          </Empty>
        </Card>
      ) : null}

      {report ? (
        <Card title="日报信息">
          <Descriptions column={{ xs: 1, md: 3 }}>
            <Descriptions.Item label="日报ID">{report.id}</Descriptions.Item>
            <Descriptions.Item label="日期">{report.report_date}</Descriptions.Item>
            <Descriptions.Item label="生成时间">{report.generated_at}</Descriptions.Item>
          </Descriptions>
        </Card>
      ) : null}

      {report ? (
        <Card title="关联论文">
          <PaperTable
            papers={reportPapersQuery.data ?? []}
            loading={reportPapersQuery.isLoading}
            onViewDetail={(paper) => setDetailPaperId(paper.id)}
            onReadOriginal={(paper) => {
              const target = paper.pdf_url || paper.online_url;
              if (!target) {
                messageApi.warning('该论文无可用链接');
                return;
              }
              window.open(target, '_blank', 'noopener,noreferrer');
            }}
            onAIInterpret={async (paper) => {
              setAiSubmittingIds((current) => {
                const next = new Set(current);
                next.add(paper.id);
                return next;
              });

              try {
                const markdown = await getPaperAiInterpretMarkdown(paper.id);
                setAiSubmittingIds((current) => {
                  const next = new Set(current);
                  next.delete(paper.id);
                  return next;
                });
                setAiMarkdownPaper(paper);
                setAiMarkdownPath(markdown.local_md_path);
                setAiMarkdownContent(markdown.content);
                return;
              } catch (error) {
                if (!(error instanceof ApiError) || error.status !== 404) {
                  setAiSubmittingIds((current) => {
                    const next = new Set(current);
                    next.delete(paper.id);
                    return next;
                  });
                  messageApi.error(`AI解读读取失败: ${(error as Error).message}`);
                  return;
                }
              }

              aiMutation.mutate(paper.id);
            }}
            onAddNote={(paper) => {
              setNotePaper(paper);
              setNoteDraft(paper.user_notes ?? '');
            }}
            onToggleLike={(paper) => {
              const nextLike: -1 | 0 | 1 = paper.like === 1 ? 0 : 1;
              setLikeSubmittingIds((current) => {
                const next = new Set(current);
                next.add(paper.id);
                return next;
              });
              likeMutation.mutate({ paperId: paper.id, like: nextLike });
            }}
            onToggleDislike={(paper) => {
              const nextLike: -1 | 0 | 1 = paper.like === -1 ? 0 : -1;
              setLikeSubmittingIds((current) => {
                const next = new Set(current);
                next.add(paper.id);
                return next;
              });
              likeMutation.mutate({ paperId: paper.id, like: nextLike });
            }}
            aiSubmittingIds={aiSubmittingIds}
            likeSubmittingIds={likeSubmittingIds}
          />
        </Card>
      ) : null}

      {report ? (
        <Card title="日报正文">
          {reportMarkdownQuery.isLoading ? <Spin /> : null}
          {markdownUnavailable ? (
            <Alert type="warning" showIcon message="日报内容文件不可用" />
          ) : null}
          {reportMarkdownQuery.error && !markdownUnavailable ? (
            <Alert
              type="error"
              showIcon
              message="日报内容加载失败"
              description={(reportMarkdownQuery.error as Error).message}
            />
          ) : null}
          {reportMarkdownQuery.data?.content ? (
            <MarkdownViewer content={reportMarkdownQuery.data.content} />
          ) : null}
        </Card>
      ) : null}

      <Modal
        title="论文详情"
        open={Boolean(detailPaperId)}
        onCancel={() => setDetailPaperId(null)}
        footer={null}
        width={900}
        destroyOnClose
      >
        {detailQuery.isLoading ? <Spin /> : null}
        {detailQuery.error ? (
          <Alert
            type="error"
            showIcon
            message="详情加载失败"
            description={(detailQuery.error as Error).message}
          />
        ) : null}
        {detailCards}
      </Modal>

      <Modal
        title="添加笔记"
        open={Boolean(notePaper)}
        destroyOnClose
        onCancel={() => setNotePaper(null)}
        onOk={() => {
          if (!notePaper) {
            return;
          }
          noteMutation.mutate({ paperId: notePaper.id, userNotes: noteDraft });
        }}
        okText="保存"
        confirmLoading={noteMutation.isPending}
      >
        <textarea
          value={noteDraft}
          rows={8}
          onChange={(event) => setNoteDraft(event.target.value)}
          style={{ width: '100%', borderRadius: 8, border: '1px solid #d9d9d9', padding: 10 }}
          placeholder="输入你的笔记"
        />
      </Modal>

      <Modal
        title={aiMarkdownPaper ? `AI解读 - ${aiMarkdownPaper.title}` : 'AI解读'}
        open={Boolean(aiMarkdownPaper)}
        onCancel={() => {
          setAiMarkdownPaper(null);
          setAiMarkdownPath('');
          setAiMarkdownContent('');
        }}
        footer={null}
        width={900}
        destroyOnClose
      >
        {aiMarkdownPath ? (
          <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
            文件路径: {aiMarkdownPath}
          </Typography.Paragraph>
        ) : null}
        <MarkdownViewer content={aiMarkdownContent} />
      </Modal>
    </Space>
  );
}
