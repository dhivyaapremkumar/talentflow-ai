import { useState } from 'react';
import { HandCoins, Plus } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { createOffer, getFunnelReport, listOffers, transitionOffer } from '../../api/resources';
import { useActor } from '../../context/ActorContext';
import { useToast } from '../../context/ToastContext';
import { Card, KPICard } from '../../components/Card';
import { Button } from '../../components/Button';
import { StatusBadge } from '../../components/Badge';
import { DataTable, type Column } from '../../components/DataTable';
import { ErrorState, EmptyState, SkeletonRows } from '../../components/States';
import { FilterBar, FilterSelect } from '../../components/FilterBar';
import { Dialog } from '../../components/Dialog';
import { FormField, Input, Select } from '../../components/Form';
import { ApiError } from '../../api/client';
import type { Offer, OfferStatus } from '../../types/api';
import dashStyles from '../Dashboard.module.css';

const STATUS_OPTIONS: OfferStatus[] = [
  'Drafted',
  'PendingApproval',
  'Approved',
  'Extended',
  'Accepted',
  'Declined',
  'Rescinded',
  'Expired',
];

const NEXT_STATUS: Record<OfferStatus, OfferStatus[]> = {
  Drafted: ['PendingApproval'],
  PendingApproval: ['Approved'],
  Approved: ['Extended', 'Rescinded'],
  Extended: ['Accepted', 'Declined', 'Rescinded', 'Expired'],
  Accepted: [],
  Declined: [],
  Rescinded: [],
  Expired: [],
};

function pct(v: number | null | undefined) {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(0)}%`;
}

export default function Offers() {
  const { currentActorId } = useActor();
  const { notify } = useToast();
  const [status, setStatus] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [transitionTarget, setTransitionTarget] = useState<Offer | null>(null);
  const [targetStatus, setTargetStatus] = useState<OfferStatus | ''>('');
  const [transitioning, setTransitioning] = useState(false);

  const offers = useApi(() => listOffers({ status: status || undefined, limit: 100 }), [status]);
  const funnel = useApi(getFunnelReport, []);

  const acceptance = funnel.data?.offer_acceptance_rate_overall[0];

  const handleTransition = async () => {
    if (!transitionTarget || !targetStatus || !currentActorId) return;
    setTransitioning(true);
    try {
      await transitionOffer(transitionTarget.offer_id, { to_status: targetStatus, actor_id: currentActorId });
      notify('success', `Offer moved to ${targetStatus}.`);
      setTransitionTarget(null);
      setTargetStatus('');
      offers.refetch();
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Transition failed.');
    } finally {
      setTransitioning(false);
    }
  };

  const columns: Column<Offer>[] = [
    { key: 'id', header: 'Offer', render: (o) => <span className={dashStyles.monoId}>{o.offer_id}</span> },
    { key: 'application', header: 'Application', render: (o) => <span className={dashStyles.monoId}>{o.application_id}</span> },
    {
      key: 'salary',
      header: 'Proposed Salary',
      render: (o) => `$${o.proposed_salary.toLocaleString()}`,
      sortValue: (o) => o.proposed_salary,
    },
    { key: 'status', header: 'Status', render: (o) => <StatusBadge status={o.status} /> },
    { key: 'approver', header: 'Approved By', render: (o) => o.approved_by_actor_id ?? '—' },
    {
      key: 'actions',
      header: 'Actions',
      render: (o) =>
        (NEXT_STATUS[o.status]?.length ?? 0) > 0 ? (
          <Button size="sm" variant="secondary" onClick={() => setTransitionTarget(o)}>
            Transition
          </Button>
        ) : (
          '—'
        ),
    },
  ];

  return (
    <div className={dashStyles.page}>
      <div className={dashStyles.pageHeader}>
        <div>
          <h1 className={dashStyles.pageTitle}>Offers & Decision Intelligence</h1>
          <p className={dashStyles.pageSubtitle}>Offer lifecycle, salary-band compliance, and acceptance analytics.</p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> Draft Offer
        </Button>
      </div>

      <div className={dashStyles.kpiGrid} style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <KPICard
          label="Acceptance Rate"
          value={funnel.loading ? '—' : pct(acceptance?.acceptance_rate)}
          context={funnel.loading ? undefined : `${acceptance?.accepted_count ?? 0} of ${acceptance?.extended_count ?? 0} extended`}
          tone="success"
          icon={<HandCoins size={16} />}
        />
        <KPICard
          label="Total Offers"
          value={offers.loading ? '—' : String(offers.data?.total ?? 0)}
          icon={<HandCoins size={16} />}
        />
        <KPICard
          label="Currently Extended"
          value={offers.loading ? '—' : String(offers.data?.items.filter((o) => o.status === 'Extended').length ?? 0)}
          context="awaiting candidate decision"
          tone="warning"
          icon={<HandCoins size={16} />}
        />
      </div>

      <Card padded={false}>
        <div style={{ padding: '20px 20px 0' }}>
          <FilterBar>
            <FilterSelect value={status} onChange={setStatus} options={STATUS_OPTIONS.map((s) => ({ value: s, label: s }))} placeholder="All statuses" />
          </FilterBar>
        </div>

        {offers.loading ? (
          <div style={{ padding: '0 20px 20px' }}>
            <SkeletonRows rows={6} height={40} />
          </div>
        ) : offers.error ? (
          <div style={{ padding: '0 20px 20px' }}>
            <ErrorState error={offers.error} onRetry={offers.refetch} />
          </div>
        ) : (offers.data?.items.length ?? 0) === 0 ? (
          <EmptyState icon={<HandCoins size={22} />} title="No offers match this filter" />
        ) : (
          <DataTable columns={columns} rows={offers.data!.items} getRowKey={(o) => o.offer_id} />
        )}
      </Card>

      <CreateOfferDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => offers.refetch()} />

      <Dialog
        open={!!transitionTarget}
        onClose={() => setTransitionTarget(null)}
        title={`Transition ${transitionTarget?.offer_id ?? ''}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setTransitionTarget(null)}>
              Cancel
            </Button>
            <Button variant="primary" loading={transitioning} disabled={!targetStatus} onClick={handleTransition}>
              Confirm
            </Button>
          </>
        }
      >
        <FormField label="New status" required hint="Approving requires the APPROVER role for the currently acting-as actor">
          <Select value={targetStatus} onChange={(e) => setTargetStatus(e.target.value as OfferStatus)}>
            <option value="">Select…</option>
            {(transitionTarget ? NEXT_STATUS[transitionTarget.status] : []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </FormField>
      </Dialog>
    </div>
  );
}

function CreateOfferDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const { notify } = useToast();
  const [applicationId, setApplicationId] = useState('');
  const [salary, setSalary] = useState('');
  const [equity, setEquity] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    if (!applicationId.trim() || !salary) {
      setError('Application ID and proposed salary are required.');
      return;
    }
    setSubmitting(true);
    try {
      await createOffer({
        application_id: applicationId.trim(),
        proposed_salary: Number(salary),
        equity_amount: equity ? Number(equity) : undefined,
      });
      notify('success', 'Offer drafted.');
      onCreated();
      onClose();
      setApplicationId('');
      setSalary('');
      setEquity('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Offer creation failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Draft New Offer"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={submitting} onClick={handleSubmit}>
            Create
          </Button>
        </>
      }
    >
      {error && <p style={{ color: 'var(--color-red-600)', fontSize: 13, marginBottom: 12, fontWeight: 600 }}>{error}</p>}
      <FormField label="Application ID" required hint="Application must be at stage 'Offer'">
        <Input value={applicationId} onChange={(e) => setApplicationId(e.target.value)} placeholder="APP-REQ-00001-CAND-000003" />
      </FormField>
      <FormField label="Proposed Salary (USD)" required hint="Must fall within the requisition's approved salary band">
        <Input type="number" value={salary} onChange={(e) => setSalary(e.target.value)} placeholder="120000" />
      </FormField>
      <FormField label="Equity (optional)">
        <Input type="number" value={equity} onChange={(e) => setEquity(e.target.value)} placeholder="0" />
      </FormField>
    </Dialog>
  );
}
