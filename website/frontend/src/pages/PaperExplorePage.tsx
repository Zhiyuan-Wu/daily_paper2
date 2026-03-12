import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Typography,
  message,
} from 'antd';
import { useMemo, useState } from 'react';

import {
  ApiError,
  createAiInterpretTask,
  getExplorePapers,
  getPaperAiInterpretMarkdown,
  getPaperDetail,
  updatePaperLike,
  updatePaperNotes,
} from '../api/client';
import type { PaperRow } from '../api/types';
import { MarkdownViewer } from '../components/MarkdownViewer';
import { PaperTable } from '../components/PaperTable';

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'arxiv', label: 'arXiv' },
  { value: 'huggingface', label: 'HuggingFace' },
];

function likeLabel(value: -1 | 0 | 1): string {
  if (value === 1) {
    return '喜欢';
  }
  if (value === -1) {
    return '不喜欢';
  }
  return '无信息';
}

export function PaperExplorePage() {
  const queryClient = useQueryClient();
  const [messageApi, contextHolder] = message.useMessage();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [source, setSource] = useState('');

  const [detailPaperId, setDetailPaperId] = useState<string | null>(null);
  const [notePaper, setNotePaper] = useState<PaperRow | null>(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [aiMarkdownPaper, setAiMarkdownPaper] = useState<PaperRow | null>(null);
  const [aiMarkdownPath, setAiMarkdownPath] = useState('');
  const [aiMarkdownContent, setAiMarkdownContent] = useState('');
  const [aiSubmittingIds, setAiSubmittingIds] = useState<Set<string>>(new Set());
  const [likeSubmittingIds, setLikeSubmittingIds] = useState<Set<string>>(new Set());

  const exploreQuery = useQuery({
    queryKey: ['papers-explore', page, pageSize, keyword, source],
    queryFn: () => getExplorePapers({ page, pageSize, keyword, source }),
    staleTime: 10_000,
  });

  const detailQuery = useQuery({
    queryKey: ['paper-detail', detailPaperId],
    queryFn: () => getPaperDetail(detailPaperId ?? ''),
    enabled: Boolean(detailPaperId),
  });

  const noteMutation = useMutation({
    mutationFn: ({ paperId, userNotes }: { paperId: string; userNotes: string }) =>
      updatePaperNotes(paperId, userNotes),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['papers-explore'] });
      if (detailPaperId) {
        void queryClient.invalidateQueries({ queryKey: ['paper-detail', detailPaperId] });
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
      void queryClient.invalidateQueries({ queryKey: ['papers-explore'] });
      if (detailPaperId) {
        void queryClient.invalidateQueries({ queryKey: ['paper-detail', detailPaperId] });
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

  const papers = exploreQuery.data?.items ?? [];

  const handleSearch = () => {
    setKeyword(keywordInput.trim());
    setPage(1);
  };

  const openDetail = (paper: PaperRow) => {
    setDetailPaperId(paper.id);
  };

  const openOriginal = (paper: PaperRow) => {
    const target = paper.pdf_url || paper.online_url;
    if (!target) {
      messageApi.warning('该论文无可用链接');
      return;
    }
    window.open(target, '_blank', 'noopener,noreferrer');
  };

  const submitAIInterpret = async (paper: PaperRow) => {
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
  };

  const openNoteModal = (paper: PaperRow) => {
    setNotePaper(paper);
    setNoteDraft(paper.user_notes ?? '');
  };

  const toggleLike = (paper: PaperRow) => {
    const nextLike: -1 | 0 | 1 = paper.like === 1 ? 0 : 1;
    setLikeSubmittingIds((current) => {
      const next = new Set(current);
      next.add(paper.id);
      return next;
    });
    likeMutation.mutate({ paperId: paper.id, like: nextLike });
  };

  const toggleDislike = (paper: PaperRow) => {
    const nextLike: -1 | 0 | 1 = paper.like === -1 ? 0 : -1;
    setLikeSubmittingIds((current) => {
      const next = new Set(current);
      next.add(paper.id);
      return next;
    });
    likeMutation.mutate({ paperId: paper.id, like: nextLike });
  };

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
        论文探索
      </Typography.Title>

      <Card>
        <Form layout="vertical" onFinish={handleSearch}>
          <Row gutter={12}>
            <Col xs={24} md={10}>
              <Form.Item label="关键字">
                <Input
                  value={keywordInput}
                  placeholder="输入标题/摘要关键字"
                  onChange={(event) => setKeywordInput(event.target.value)}
                  onPressEnter={handleSearch}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item label="来源">
                <Select
                  options={SOURCE_OPTIONS}
                  value={source}
                  onChange={(value) => {
                    setSource(value);
                    setPage(1);
                  }}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label=" ">
                <Button type="primary" onClick={handleSearch} block>
                  查询
                </Button>
              </Form.Item>
            </Col>
          </Row>
        </Form>

        {exploreQuery.error ? (
          <Alert
            type="error"
            showIcon
            message="数据加载失败"
            description={(exploreQuery.error as Error).message}
          />
        ) : null}

        {papers.length === 0 && !exploreQuery.isLoading ? (
          <Empty description="暂无匹配论文" />
        ) : (
          <PaperTable
            papers={papers}
            loading={exploreQuery.isLoading}
            total={exploreQuery.data?.total ?? 0}
            page={page}
            pageSize={pageSize}
            onPageChange={(nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            }}
            onViewDetail={openDetail}
            onReadOriginal={openOriginal}
            onAIInterpret={submitAIInterpret}
            onAddNote={openNoteModal}
            onToggleLike={toggleLike}
            onToggleDislike={toggleDislike}
            aiSubmittingIds={aiSubmittingIds}
            likeSubmittingIds={likeSubmittingIds}
          />
        )}
      </Card>

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
        <Input.TextArea
          value={noteDraft}
          rows={8}
          onChange={(event) => setNoteDraft(event.target.value)}
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
