import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UserSearch } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { listApplications } from '../../api/resources';
import { Card } from '../../components/Card';
import { DataTable, Pagination, type Column } from '../../components/DataTable';
import { ErrorState, EmptyState, SkeletonRows } from '../../components/States';
import { FilterBar, FilterSelect } from '../../components/FilterBar';
import { StatusBadge } from '../../components/Badge';
import type { Application } from '../../types/api';
import styles from '../Dashboard.module.css';

const STAGE_OPTIONS = ['Applied', 'Screening', 'Interviewing', 'Offer', 'Hired', 'Rejected', 'Withdrawn'].map((s) => ({
  value: s,
  label: s,
}));
const LIMIT = 20;

export default function ScreeningList() {
  const navigate = useNavigate();
  const [stage, setStage] = useState('');
  const [offset, setOffset] = useState(0);

  const { data, loading, error, refetch } = useApi(
    () => listApplications({ stage: stage || undefined, limit: LIMIT, offset }),
    [stage, offset],
  );

  const columns: Column<Application>[] = [
    { key: 'candidate', header: 'Candidate', render: (a) => <strong>{a.candidate_name ?? a.candidate_id}</strong>, sortValue: (a) => a.candidate_name ?? '' },
    { key: 'requisition', header: 'Requisition', render: (a) => a.requisition_title ?? a.requisition_id },
    { key: 'stage', header: 'Stage', render: (a) => <StatusBadge status={a.stage} /> },
    {
      key: 'score',
      header: 'Score',
      render: (a) => (a.screening_score !== null ? a.screening_score.toFixed(2) : '—'),
      sortValue: (a) => a.screening_score,
    },
    { key: 'decision', header: 'Decision', render: (a) => (a.screening_decision ? <StatusBadge status={a.screening_decision} /> : '—') },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Screening & Candidates</h1>
          <p className={styles.pageSubtitle}>Deterministic screening results and candidate profiles for every application.</p>
        </div>
      </div>

      <Card padded={false}>
        <div style={{ padding: '20px 20px 0' }}>
          <FilterBar>
            <FilterSelect value={stage} onChange={(v) => { setStage(v); setOffset(0); }} options={STAGE_OPTIONS} placeholder="All stages" />
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
        ) : (data?.items.length ?? 0) === 0 ? (
          <EmptyState icon={<UserSearch size={22} />} title="No applications match this filter" />
        ) : (
          <>
            <DataTable columns={columns} rows={data!.items} getRowKey={(a) => a.application_id} onRowClick={(a) => navigate(`/screening/${a.application_id}`)} />
            {data && <Pagination total={data.total} limit={LIMIT} offset={offset} onOffsetChange={setOffset} />}
          </>
        )}
      </Card>
    </div>
  );
}
