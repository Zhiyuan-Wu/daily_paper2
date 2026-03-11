import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { PaperRow } from '../api/types';
import { PaperTable } from './PaperTable';

const SAMPLE_PAPER: PaperRow = {
  id: 'arxiv:2603.00001',
  title: 'Agentic Critical Training',
  authors: ['Alice'],
  keywords: ['agent', 'llm'],
  published_at: '2026-03-11T10:00:00+00:00',
  source: 'arxiv',
  online_url: 'https://example.org/paper',
  pdf_url: 'https://example.org/paper.pdf',
  abstract: 'abstract',
  extra: {},
  local_pdf_path: null,
  local_text_path: null,
  recommendation_records: [],
  user_notes: '',
  ai_report_summary: '',
  ai_report_path: '',
};

describe('PaperTable', () => {
  it('triggers row action callbacks', async () => {
    const user = userEvent.setup();
    const onViewDetail = vi.fn();
    const onReadOriginal = vi.fn();
    const onAIInterpret = vi.fn();
    const onAddNote = vi.fn();

    render(
      <PaperTable
        papers={[SAMPLE_PAPER]}
        loading={false}
        onViewDetail={onViewDetail}
        onReadOriginal={onReadOriginal}
        onAIInterpret={onAIInterpret}
        onAddNote={onAddNote}
      />, 
    );

    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(4);

    await user.click(buttons[0]);
    await user.click(buttons[1]);
    await user.click(buttons[2]);
    await user.click(buttons[3]);

    expect(onViewDetail).toHaveBeenCalledWith(SAMPLE_PAPER);
    expect(onReadOriginal).toHaveBeenCalledWith(SAMPLE_PAPER);
    expect(onAIInterpret).toHaveBeenCalledWith(SAMPLE_PAPER);
    expect(onAddNote).toHaveBeenCalledWith(SAMPLE_PAPER);
  });
});
