import { useState } from 'react';
import { CalendarPlus, CheckCircle2, MessageSquarePlus, XCircle } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import {
  getInterviewerAvailability,
  listInterviewers,
  listInterviews,
  scheduleInterview,
  submitFeedback,
  transitionInterviewStatus,
} from '../../api/resources';
import { useToast } from '../../context/ToastContext';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { StatusBadge } from '../../components/Badge';
import { DataTable, type Column } from '../../components/DataTable';
import { ErrorState, EmptyState, SkeletonRows } from '../../components/States';
import { FilterBar, FilterSelect } from '../../components/FilterBar';
import { Dialog } from '../../components/Dialog';
import { FormField, Input, Select } from '../../components/Form';
import { ApiError } from '../../api/client';
import type { Interview } from '../../types/api';
import dashStyles from '../Dashboard.module.css';

const STATUS_OPTIONS = ['Scheduled', 'Completed', 'Cancelled', 'NoShow'].map((s) => ({ value: s, label: s }));
const ROUND_TYPES = ['Phone', 'Technical', 'Onsite', 'Panel', 'HiringManager'];

export default function Interviews() {
  const { notify } = useToast();
  const [status, setStatus] = useState('');
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [feedbackTarget, setFeedbackTarget] = useState<Interview | null>(null);

  const interviews = useApi(() => listInterviews({ status: status || undefined, limit: 100 }), [status]);
  const interviewers = useApi(listInterviewers, []);

  const columns: Column<Interview>[] = [
    { key: 'id', header: 'Interview', render: (i) => <span className={dashStyles.monoId}>{i.interview_id}</span> },
    { key: 'application', header: 'Application', render: (i) => <span className={dashStyles.monoId}>{i.application_id}</span> },
    { key: 'interviewer', header: 'Interviewer', render: (i) => i.interviewer_id },
    { key: 'round', header: 'Round', render: (i) => `#${i.round_number} ${i.round_type}` },
    {
      key: 'when',
      header: 'Scheduled',
      render: (i) => new Date(i.scheduled_start).toLocaleString(),
      sortValue: (i) => i.scheduled_start,
    },
    { key: 'status', header: 'Status', render: (i) => <StatusBadge status={i.status} /> },
    {
      key: 'actions',
      header: 'Actions',
      render: (i) =>
        i.status === 'Scheduled' ? (
          <div style={{ display: 'flex', gap: 6 }}>
            <Button size="sm" variant="secondary" onClick={() => handleStatus(i, 'Completed')}>
              <CheckCircle2 size={12} /> Complete
            </Button>
            <Button size="sm" variant="ghost" onClick={() => handleStatus(i, 'NoShow')}>
              <XCircle size={12} /> No-show
            </Button>
          </div>
        ) : i.status === 'Completed' ? (
          <Button size="sm" variant="secondary" onClick={() => setFeedbackTarget(i)}>
            <MessageSquarePlus size={12} /> Feedback
          </Button>
        ) : (
          '—'
        ),
    },
  ];

  const handleStatus = async (interview: Interview, to_status: string) => {
    try {
      await transitionInterviewStatus(interview.interview_id, to_status);
      notify('success', `Interview marked ${to_status}.`);
      interviews.refetch();
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Status update failed.');
    }
  };

  return (
    <div className={dashStyles.page}>
      <div className={dashStyles.pageHeader}>
        <div>
          <h1 className={dashStyles.pageTitle}>Interview Management</h1>
          <p className={dashStyles.pageSubtitle}>Scheduling, availability, and feedback for every interview round.</p>
        </div>
        <Button variant="primary" onClick={() => setScheduleOpen(true)}>
          <CalendarPlus size={15} /> Schedule Interview
        </Button>
      </div>

      <Card padded={false}>
        <div style={{ padding: '20px 20px 0' }}>
          <FilterBar>
            <FilterSelect value={status} onChange={setStatus} options={STATUS_OPTIONS} placeholder="All statuses" />
          </FilterBar>
        </div>

        {interviews.loading ? (
          <div style={{ padding: '0 20px 20px' }}>
            <SkeletonRows rows={6} height={40} />
          </div>
        ) : interviews.error ? (
          <div style={{ padding: '0 20px 20px' }}>
            <ErrorState error={interviews.error} onRetry={interviews.refetch} />
          </div>
        ) : (interviews.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="No interviews match this filter" />
        ) : (
          <DataTable columns={columns} rows={interviews.data!.items} getRowKey={(i) => i.interview_id} />
        )}
      </Card>

      <ScheduleDialog
        open={scheduleOpen}
        onClose={() => setScheduleOpen(false)}
        interviewerOptions={interviewers.data ?? []}
        onScheduled={() => interviews.refetch()}
      />
      <FeedbackDialog interview={feedbackTarget} onClose={() => setFeedbackTarget(null)} onSubmitted={() => interviews.refetch()} />
    </div>
  );
}

function ScheduleDialog({
  open,
  onClose,
  interviewerOptions,
  onScheduled,
}: {
  open: boolean;
  onClose: () => void;
  interviewerOptions: { interviewer_id: string; full_name: string }[];
  onScheduled: () => void;
}) {
  const { notify } = useToast();
  const [applicationId, setApplicationId] = useState('');
  const [interviewerId, setInterviewerId] = useState('');
  const [roundType, setRoundType] = useState('Phone');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const availability = useApi(
    () => (interviewerId ? getInterviewerAvailability(interviewerId) : Promise.resolve([])),
    [interviewerId],
  );

  const handleSubmit = async () => {
    setError(null);
    if (!applicationId.trim() || !interviewerId || !start || !end) {
      setError('All fields are required.');
      return;
    }
    setSubmitting(true);
    try {
      await scheduleInterview({
        application_id: applicationId.trim(),
        interviewer_id: interviewerId,
        round_type: roundType,
        scheduled_start: start,
        scheduled_end: end,
      });
      notify('success', 'Interview scheduled.');
      onScheduled();
      onClose();
      setApplicationId('');
      setInterviewerId('');
      setStart('');
      setEnd('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Scheduling failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Schedule Interview"
      width={520}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={submitting} onClick={handleSubmit}>
            Schedule
          </Button>
        </>
      }
    >
      {error && (
        <p style={{ color: 'var(--color-red-600)', fontSize: 13, marginBottom: 12, fontWeight: 600 }}>{error}</p>
      )}
      <FormField label="Application ID" required hint="Application must be at stage 'Interviewing'">
        <Input value={applicationId} onChange={(e) => setApplicationId(e.target.value)} placeholder="APP-REQ-00001-CAND-000003" />
      </FormField>
      <FormField label="Interviewer" required>
        <Select value={interviewerId} onChange={(e) => setInterviewerId(e.target.value)}>
          <option value="">Select interviewer…</option>
          {interviewerOptions.map((i) => (
            <option key={i.interviewer_id} value={i.interviewer_id}>
              {i.full_name} ({i.interviewer_id})
            </option>
          ))}
        </Select>
      </FormField>
      {interviewerId && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: -8, marginBottom: 12 }}>
          {availability.loading
            ? 'Loading availability…'
            : `${availability.data?.length ?? 0} availability slot(s) on file for this interviewer.`}
        </p>
      )}
      <FormField label="Round Type" required>
        <Select value={roundType} onChange={(e) => setRoundType(e.target.value)}>
          {ROUND_TYPES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField label="Start" required>
        <Input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
      </FormField>
      <FormField label="End" required>
        <Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
      </FormField>
    </Dialog>
  );
}

function FeedbackDialog({
  interview,
  onClose,
  onSubmitted,
}: {
  interview: Interview | null;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const { notify } = useToast();
  const [recommendation, setRecommendation] = useState('Yes');
  const [score, setScore] = useState(3);
  const [strengths, setStrengths] = useState('');
  const [concerns, setConcerns] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!interview) return null;

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await submitFeedback(interview.interview_id, {
        interviewer_id: interview.interviewer_id,
        recommendation,
        overall_score: score,
        submitted_at: new Date().toISOString(),
        strengths_text: strengths || undefined,
        concerns_text: concerns || undefined,
      });
      notify('success', 'Feedback submitted.');
      onSubmitted();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Feedback submission failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Submit Feedback — ${interview.interview_id}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={submitting} onClick={handleSubmit}>
            Submit
          </Button>
        </>
      }
    >
      {error && <p style={{ color: 'var(--color-red-600)', fontSize: 13, marginBottom: 12, fontWeight: 600 }}>{error}</p>}
      <FormField label="Recommendation" required>
        <Select value={recommendation} onChange={(e) => setRecommendation(e.target.value)}>
          {['StrongYes', 'Yes', 'No', 'StrongNo'].map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField label="Overall Score (1-5)" required>
        <Input type="number" min={1} max={5} value={score} onChange={(e) => setScore(Number(e.target.value))} />
      </FormField>
      <FormField label="Strengths">
        <Input value={strengths} onChange={(e) => setStrengths(e.target.value)} />
      </FormField>
      <FormField label="Concerns">
        <Input value={concerns} onChange={(e) => setConcerns(e.target.value)} />
      </FormField>
    </Dialog>
  );
}
