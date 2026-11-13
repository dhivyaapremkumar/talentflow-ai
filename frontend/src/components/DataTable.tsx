import { useMemo, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import styles from './DataTable.module.css';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number | null;
  width?: string;
}

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  onRowClick,
  emptyMessage = 'No records match the current filters.',
}: {
  columns: Column<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
}) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortValue) return rows;
    const withValues = rows.map((r) => ({ row: r, v: col.sortValue!(r) }));
    withValues.sort((a, b) => {
      if (a.v === null && b.v === null) return 0;
      if (a.v === null) return 1;
      if (b.v === null) return -1;
      if (a.v < b.v) return sortDir === 'asc' ? -1 : 1;
      if (a.v > b.v) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return withValues.map((w) => w.row);
  }, [rows, sortKey, sortDir, columns]);

  const toggleSort = (key: string) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDir('asc');
    } else {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    }
  };

  if (rows.length === 0) {
    return <div className={styles.emptyCell}>{emptyMessage}</div>;
  }

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} style={{ width: col.width }}>
                {col.sortValue ? (
                  <button className={styles.sortBtn} onClick={() => toggleSort(col.key)}>
                    {col.header}
                    {sortKey === col.key ? (
                      sortDir === 'asc' ? (
                        <ArrowUp size={12} />
                      ) : (
                        <ArrowDown size={12} />
                      )
                    ) : (
                      <ArrowUpDown size={12} className={styles.sortIconIdle} />
                    )}
                  </button>
                ) : (
                  col.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr key={getRowKey(row)} className={onRowClick ? styles.clickable : ''} onClick={() => onRowClick?.(row)}>
              {columns.map((col) => (
                <td key={col.key}>{col.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({
  total,
  limit,
  offset,
  onOffsetChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.ceil(total / limit);
  return (
    <div className={styles.pagination}>
      <span className={styles.pageInfo}>
        Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
      </span>
      <div className={styles.pageControls}>
        <button className={styles.pageBtn} disabled={page <= 1} onClick={() => onOffsetChange(Math.max(0, offset - limit))}>
          <ChevronLeft size={16} />
        </button>
        <span className={styles.pageLabel}>
          Page {page} of {pageCount}
        </span>
        <button
          className={styles.pageBtn}
          disabled={page >= pageCount}
          onClick={() => onOffsetChange(offset + limit)}
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
