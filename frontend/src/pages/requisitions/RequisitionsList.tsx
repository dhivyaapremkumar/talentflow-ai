import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Briefcase } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { listRequisitions } from '../../api/resources';
import { Card } from '../../components/Card';
import { DataTable, Pagination, type Column } from '../../components/DataTable';
import { ErrorState, EmptyState, SkeletonRows } from '../../components/States';
import { FilterBar, FilterSelect, SearchInput } from '../../components/FilterBar';
import { StatusBadge } from '../../components/Badge';
import type { Requisition } from '../../types/api';
import styles from '../Dashboard.module.css';

const STATUS_OPTIONS = ['Draft', 'PendingApproval', 'Approved', 'Open', 'OnHold', 'Closed', 'Cancelled'].map((s) => ({
  value: s,
  label: s,
}));

const LIMIT = 20;

export default function RequisitionsList() {
  const navigate = useNavigate();
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);

  const { data, loading, error, refetch } = useApi(
    () => listRequisitions({ status: status || undefined, limit: LIMIT, offset }),
    [status, offset],
  );

  const filteredItems = useMemo(() => {
    if (!data) return [];
    if (!search.trim()) return data.items;
    const q = search.toLowerCase();
    return data.items.filter((r) => r.title.toLowerCase().includes(q) || r.requisition_id.toLowerCase().includes(q));
  }, [data, search]);

  const columns: Column<Requisition>[] = [
    { key: 'id', header: 'Requisition', render: (r) => <span className={styles.monoId}>{r.requisition_id}</span> },
    { key: 'title', header: 'Title', render: (r) => <strong>{r.title}</strong>, sortValue: (r) => r.title },
    { key: 'level', header: 'Level', render: (r) => r.level },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
    {
      key: 'salary',
      header: 'Salary Band',
      render: (r) => `$${r.salary_min.toLocaleString()} – $${r.salary_max.toLocaleString()}`,
      sortValue: (r) => r.salary_min,
    },
    { key: 'headcount', header: 'Headcount', render: (r) => r.headcount, sortValue: (r) => r.headcount },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Requisitions & Applications</h1>
          <p className={styles.pageSubtitle}>Browse open roles and drill into every application against them.</p>
        </div>
      </div>

      <Card padded={false}>
        <div style={{ padding: '20px 20px 0' }}>
          <FilterBar>
            <SearchInput value={search} onChange={setSearch} placeholder="Search by title or ID…" />
            <FilterSelect value={status} onChange={(v) => { setStatus(v); setOffset(0); }} options={STATUS_OPTIONS} placeholder="All statuses" />
          </FilterBar>
        </div>

        {loading ? (
          <div style={{ padding: '0 20px 20px' }}>
            <SkeletonRows rows={6} height={40} />
          </div>
        ) : error ? (
          <div style={{ padding: '0 20px 20px' }}>
            <ErrorState error={error} onRetry={refetch} />
          </div>
        ) : filteredItems.length === 0 ? (
          <EmptyState
            icon={<Briefcase size={22} />}
            title="No requisitions match these filters"
            description="Try clearing the status filter or search term."
          />
        ) : (
          <>
            <DataTable columns={columns} rows={filteredItems} getRowKey={(r) => r.requisition_id} onRowClick={(r) => navigate(`/requisitions/${r.requisition_id}`)} />
            {data && <Pagination total={data.total} limit={LIMIT} offset={offset} onOffsetChange={setOffset} />}
          </>
        )}
      </Card>
    </div>
  );
}
