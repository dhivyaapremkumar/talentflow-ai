import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Plus } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { getRequisition, listApplications, submitApplication, transitionRequisition } from '../../api/resources';
import { useActor } from '../../context/ActorContext';
import { useToast } from '../../context/ToastContext';
import { Card, CardHeader } from '../../components/Card';
import { Button } from '../../components/Button';
import { StatusBadge } from '../../components/Badge';
import { DataTable, type Column } from '../../components/DataTable';
import { ErrorState, EmptyState, SkeletonRows } from '../../components/States';
import { Dialog } from '../../components/Dialog';
import { FormField, Input, Select } from '../../components/Form';
import { ApiError } from '../../api/client';
import type { Application, RequisitionStatus } from '../../types/api';
import styles from '../Dashboard.module.css';
import detailStyles from './RequisitionDetail.module.css';

const NEXT_STATUS: Record<RequisitionStatus, RequisitionStatus[]> = {
  Draft: ['PendingApproval', 'Cancelled'],
  PendingApproval: ['Approved', 'Cancelled'],
  Approved: ['Open', 'Cancelled'],
  Open: ['OnHold', 'Closed', 'Cancelled'],
  OnHold: ['Open', 'Cancelled'],
  Closed: [],
  Cancelled: [],
};

export default function RequisitionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentActorId } = useActor();
  const { notify } = useToast();
  const [transitioning, setTransitioning] = useState(false);
  const [targetStatus, setTargetStatus] = useState('');
  const [newAppOpen, setNewAppOpen] = useState(false);
  const [newCandidateId, setNewCandidateId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const req = useApi(() => getRequisition(id!), [id]);
  const apps = useApi(() => listApplications({ requisition_id: id, limit: 100 }), [id]);

  if (req.error) return <ErrorState error={req.error} onRetry={req.refetch} />;

  const handleTransition = async () => {
    if (!targetStatus || !currentActorId) return;
    setTransitioning(true);
    try {
      await transitionRequisition(id!, { to_status: targetStatus, actor_id: currentActorId });
      notify('success', `Requisition moved to ${targetStatus}.`);
      setTargetStatus('');
      req.refetch();
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Transition failed.');
    } finally {
      setTransitioning(false);
    }
  };

  const handleSubmitApplication = async () => {
    setFormError(null);
    if (!newCandidateId.trim()) {
      setFormError('Candidate ID is required.');
      return;
    }
    setSubmitting(true);
    try {
      await submitApplication({ candidate_id: newCandidateId.trim(), requisition_id: id! });
      notify('success', 'Application submitted.');
      setNewAppOpen(false);
      setNewCandidateId('');
      apps.refetch();
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : 'Submission failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const columns: Column<Application>[] = [
    { key: 'id', header: 'Application', render: (a) => <span className={styles.monoId}>{a.application_id}</span> },
    { key: 'candidate', header: 'Candidate', render: (a) => a.candidate_name ?? a.candidate_id },
    { key: 'stage', header: 'Stage', render: (a) => <StatusBadge status={a.stage} /> },
    {
      key: 'score',
      header: 'Screening Score',
      render: (a) => (a.screening_score !== null ? a.screening_score.toFixed(2) : '—'),
      sortValue: (a) => a.screening_score,
    },
    {
      key: 'decision',
      header: 'Decision',
      render: (a) => (a.screening_decision ? <StatusBadge status={a.screening_decision} /> : '—'),
    },
  ];

  const options = req.data ? NEXT_STATUS[req.data.status] ?? [] : [];

  return (
    <div className={styles.page}>
      <button className={detailStyles.backLink} onClick={() => navigate('/requisitions')}>
        <ArrowLeft size={14} /> Back to requisitions
      </button>

      {req.loading || !req.data ? (
        <Card>
          <SkeletonRows rows={5} height={20} />
        </Card>
      ) : (
        <>
          <Card>
            <div className={detailStyles.headerRow}>
              <div>
                <div className={detailStyles.titleRow}>
                  <h1 className={styles.pageTitle}>{req.data.title}</h1>
                  <StatusBadge status={req.data.status} />
                </div>
                <p className={styles.pageSubtitle}>
                  {req.data.requisition_id} · {req.data.level} · {req.data.employment_type}
                </p>
              </div>
              {options.length > 0 && (
                <div className={detailStyles.transitionBox}>
                  <Select value={targetStatus} onChange={(e) => setTargetStatus(e.target.value)}>
                    <option value="">Move to…</option>
                    {options.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </Select>
                  <Button variant="primary" size="sm" loading={transitioning} disabled={!targetStatus} onClick={handleTransition}>
                    Apply
                  </Button>
                </div>
              )}
            </div>

            <div className={detailStyles.factGrid}>
              <div>
                <span className={detailStyles.factLabel}>Salary Band</span>
                <span className={detailStyles.factValue}>
                  ${req.data.salary_min.toLocaleString()} – ${req.data.salary_max.toLocaleString()}
                </span>
              </div>
              <div>
                <span className={detailStyles.factLabel}>Headcount</span>
                <span className={detailStyles.factValue}>{req.data.headcount}</span>
              </div>
              <div>
                <span className={detailStyles.factLabel}>Opened</span>
                <span className={detailStyles.factValue}>{req.data.opened_at ?? '—'}</span>
              </div>
              <div>
                <span className={detailStyles.factLabel}>Target Close</span>
                <span className={detailStyles.factValue}>{req.data.target_close_date ?? '—'}</span>
              </div>
            </div>
          </Card>

          <Card padded={false}>
            <div style={{ padding: '20px 20px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <CardHeader title="Applications" subtitle={`${apps.data?.total ?? 0} total for this requisition`} />
              <Button size="sm" variant="primary" onClick={() => setNewAppOpen(true)}>
                <Plus size={14} /> New Application
              </Button>
            </div>

            {apps.loading ? (
              <div style={{ padding: '0 20px 20px' }}>
                <SkeletonRows rows={5} height={36} />
              </div>
            ) : apps.error ? (
              <div style={{ padding: '0 20px 20px' }}>
                <ErrorState error={apps.error} onRetry={apps.refetch} />
              </div>
            ) : (apps.data?.items.length ?? 0) === 0 ? (
              <EmptyState title="No applications yet" description="Submit the first application for this requisition." />
            ) : (
              <DataTable
                columns={columns}
                rows={apps.data!.items}
                getRowKey={(a) => a.application_id}
                onRowClick={(a) => navigate(`/screening/${a.application_id}`)}
              />
            )}
          </Card>
        </>
      )}

      <Dialog
        open={newAppOpen}
        onClose={() => setNewAppOpen(false)}
        title="Submit New Application"
        footer={
          <>
            <Button variant="ghost" onClick={() => setNewAppOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={submitting} onClick={handleSubmitApplication}>
              Submit
            </Button>
          </>
        }
      >
        <FormField label="Candidate ID" required error={formError ?? undefined} hint="e.g. CAND-000003 (must already exist with a resume on file)">
          <Input value={newCandidateId} onChange={(e) => setNewCandidateId(e.target.value)} placeholder="CAND-000003" invalid={!!formError} />
        </FormField>
      </Dialog>
    </div>
  );
}
