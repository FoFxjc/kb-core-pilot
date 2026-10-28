import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PipeTable } from './PageContent';
import { parsePipeTable, splitRow } from './pipeTable';

const MD = '||2025 $ million|2024 $ million|+/(-) %|\n|---|---|---|---|\n|Selected Income Statement Items||||\n|Net interest income|9,150|9,755|(6)|';

describe('parsePipeTable', () => {
  it('reads the header, skips the separator and keeps empty cells', () => {
    const t = parsePipeTable(MD);
    expect(t.header).toEqual(['', '2025 $ million', '2024 $ million', '+/(-) %']);
    expect(t.rows).toEqual([
      ['Selected Income Statement Items', '', '', ''],
      ['Net interest income', '9,150', '9,755', '(6)'],
    ]);
  });

  it('handles escaped pipes, aligned separators and short rows', () => {
    expect(splitRow('| a \\| b | c |')).toEqual(['a | b', 'c']);
    const t = parsePipeTable('| x | y |\n|:--|--:|\n| 1 |');
    expect(t.header).toEqual(['x', 'y']);
    expect(t.rows).toEqual([['1', '']]);
  });

  it('has no header without a separator row, and nothing for non-table text', () => {
    expect(parsePipeTable('| 1 | 2 |\n| 3 | 4 |')).toEqual({ header: null, rows: [['1', '2'], ['3', '4']] });
    expect(parsePipeTable('just text')).toEqual({ header: null, rows: [] });
  });
});

describe('PipeTable', () => {
  it('renders the Markdown as an HTML table', () => {
    render(<PipeTable markdown={MD} />);
    expect(screen.getAllByRole('columnheader')).toHaveLength(4);
    expect(screen.getByRole('cell', { name: 'Net interest income' })).toBeTruthy();
    expect(screen.getAllByRole('row')).toHaveLength(3);
  });
});
