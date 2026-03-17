import { Alert, Card, Modal, Space, Spin, Tag } from 'antd';

import type { PaperRow } from '../api/types';
import { likeLabel } from './paperUtils';

interface PaperDetailModalProps {
  paperId: string | null;
  paper: PaperRow | undefined;
  loading: boolean;
  error: Error | null;
  onClose: () => void;
}

export function PaperDetailModal({
  paperId,
  paper,
  loading,
  error,
  onClose,
}: PaperDetailModalProps) {
  return (
    <Modal
      title="论文详情"
      open={Boolean(paperId)}
      onCancel={onClose}
      footer={null}
      width={900}
      destroyOnClose
    >
      {loading ? <Spin /> : null}
      {error ? <Alert type="error" showIcon message="详情加载失败" description={error.message} /> : null}
      {paper ? (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card title="论文信息" size="small">
            <p>
              <strong>ID:</strong> {paper.id}
            </p>
            <p>
              <strong>标题:</strong> {paper.title}
            </p>
            <p>
              <strong>作者:</strong> {paper.authors.join(', ') || '-'}
            </p>
            <p>
              <strong>关键词:</strong> <TagList values={paper.keywords} />
            </p>
            <p>
              <strong>单位:</strong> <TagList values={paper.affiliations} />
            </p>
            <p>
              <strong>摘要:</strong> {paper.abstract || '-'}
            </p>
            <p>
              <strong>来源:</strong> {paper.source}
            </p>
            <p>
              <strong>发表时间:</strong> {paper.published_at || '-'}
            </p>
            <p>
              <strong>在线链接:</strong> {paper.online_url || '-'}
            </p>
            <p>
              <strong>PDF链接:</strong> {paper.pdf_url || '-'}
            </p>
          </Card>

          <Card title="活动信息" size="small">
            <p>
              <strong>推荐记录:</strong>{' '}
              {paper.recommendation_records.length > 0 ? paper.recommendation_records.join(', ') : '-'}
            </p>
            <p>
              <strong>用户笔记:</strong> {paper.user_notes || '-'}
            </p>
            <p>
              <strong>偏好:</strong> {likeLabel(paper.like)}
            </p>
            <p>
              <strong>AI摘要:</strong> {paper.ai_report_summary || '-'}
            </p>
            <p>
              <strong>AI报告路径:</strong> {paper.ai_report_path || '-'}
            </p>
          </Card>
        </Space>
      ) : null}
    </Modal>
  );
}

function TagList({ values }: { values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <>
      {values.map((value) => (
        <Tag key={value} style={{ marginInlineEnd: 6, marginBottom: 6 }}>
          {value}
        </Tag>
      ))}
    </>
  );
}
