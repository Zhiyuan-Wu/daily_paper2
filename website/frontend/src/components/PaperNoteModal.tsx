import { Input, Modal } from 'antd';

import type { PaperRow } from '../api/types';

interface PaperNoteModalProps {
  paper: PaperRow | null;
  draft: string;
  saving: boolean;
  onDraftChange: (next: string) => void;
  onCancel: () => void;
  onSave: () => void;
}

export function PaperNoteModal({
  paper,
  draft,
  saving,
  onDraftChange,
  onCancel,
  onSave,
}: PaperNoteModalProps) {
  return (
    <Modal
      title="添加笔记"
      open={Boolean(paper)}
      destroyOnClose
      onCancel={onCancel}
      onOk={onSave}
      okText="保存"
      confirmLoading={saving}
    >
      <Input.TextArea
        value={draft}
        rows={8}
        onChange={(event) => onDraftChange(event.target.value)}
        placeholder="输入你的笔记"
      />
    </Modal>
  );
}
