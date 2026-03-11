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
  createAiInterpretTask,
  getExplorePapers,
  getPaperDetail,
  updatePaperNotes,
} from '../api/client';
import type { PaperRow } from '../api/types';
import { PaperTable } from '../components/PaperTable';

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'arxiv', label: 'arXiv' },
  { value: 'huggingface', label: 'HuggingFace' },
];

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
  const [aiSubmittingIds, setAiSubmittingIds] = useState<Set<string>>(new Set());

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

  const submitAIInterpret = (paper: PaperRow) => {
    setAiSubmittingIds((current) => {
      const next = new Set(current);
      next.add(paper.id);
      return next;
    });
    aiMutation.mutate(paper.id);
  };

  const openNoteModal = (paper: PaperRow) => {
    setNotePaper(paper);
    setNoteDraft(paper.user_notes ?? '');
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
            aiSubmittingIds={aiSubmittingIds}
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
    </Space>
  );
}
