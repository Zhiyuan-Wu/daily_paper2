import { Modal, Typography } from 'antd';

import type { PaperRow } from '../api/types';
import { MarkdownViewer } from './MarkdownViewer';

interface PaperAiMarkdownModalProps {
  paper: PaperRow | null;
  markdownPath: string;
  content: string;
  onClose: () => void;
}

export function PaperAiMarkdownModal({
  paper,
  markdownPath,
  content,
  onClose,
}: PaperAiMarkdownModalProps) {
  return (
    <Modal
      title={paper ? `AI解读 - ${paper.title}` : 'AI解读'}
      open={Boolean(paper)}
      onCancel={onClose}
      footer={null}
      width={900}
      destroyOnClose
    >
      {markdownPath ? (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          文件路径: {markdownPath}
        </Typography.Paragraph>
      ) : null}
      <MarkdownViewer content={content} />
    </Modal>
  );
}
