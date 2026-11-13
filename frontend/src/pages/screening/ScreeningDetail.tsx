import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Mail, MapPin, Phone, PlayCircle } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import {
  getApplication,
  getApplicationAttempts,
  getApplicationScreeningRuns,
  getCandidate,
  getCandidateResumes,
  getCandidateSkills,
  screenApplication,
  transitionApplication,
} from '../../api/resources';
import { useActor } from '../../context/ActorContext';
import { useToast } from '../../context/ToastContext';
import { Card, CardHeader } from '../../components/Card';
import { Button } from '../../components/Button';
import { StatusBadge, YesNoBadge } from '../../components/Badge';
import { DataTable, type Column } from '../../components/DataTable';
import { ErrorState, SkeletonRows } from '../../components/States';
import { Dialog } from '../../components/Dialog';
import { FormField, Input, Select } from '../../components/Form';
import { ApiError } from '../../api/client';
import type { ApplicationStage, ScreeningRun, SubmissionAttempt } from '../../types/api';
import dashStyles from '../Dashboard.module.css';
import styles from './ScreeningDetail.module.css';

const NEXT_STAGE: Record<ApplicationStage, ApplicationStage[]> = {
  Applied: ['Screening', 'Withdrawn'],
  Screening: ['Interviewing', 'Rejected', 'Withdrawn'],
  Interviewing: ['Offer', 'Rejected', 'Withdrawn'],
  Offer: ['Hired', 'Rejected', 'Withdrawn'],
  Hired: [],
  Rejected: [],
  Withdrawn: [],
};

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  const pct = value !== null ? Math.round(value * 100) : 0;
  return (
    <div className={styles.scoreRow}>
      <span className={styles.scoreLabel}>{label}</span>
      <div className={styles.scoreTrack}>
        <div className={styles.scoreFill} style={{ width: `${pct}%` }} />
      </div>
      <span className={styles.scoreValue}>{value !== null ? `${pct}%` : '—'}</span>
    </div>
  );
}

export default function ScreeningDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentActorId } = useActor();
  const { notify } = useToast();
  const [screening, setScreening] = useState(false);
  const [transitionOpen, setTransitionOpen] = useState(false);
  const [targetStage, setTargetStage] = useState<ApplicationStage | ''>('');
  const [rejectedReason, setRejectedReason] = useState('');
  const [transitioning, setTransitioning] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const app = useApi(() => getApplication(id!), [id]);
  const candidateId = app.data?.candidate_id;
  // candidateId is only known once `app` has loaded - guard each dependent
  // query so it never fires a request for a literal "undefined" id while
  // waiting (a real bug caught via a live network-request check, not an
  // assumption: the naive `getCandidate(candidateId!)` version did exactly
  // that on first render, before app.data existed).
  const candidate = useApi(() => (candidateId ? getCandidate(candidateId) : Promise.resolve(null)), [candidateId]);
  const skills = useApi(() => (candidateId ? getCandidateSkills(candidateId) : Promise.resolve([])), [candidateId]);
  const resumes = useApi(() => (candidateId ? getCandidateResumes(candidateId) : Promise.resolve([])), [candidateId]);
  const runs = useApi(() => getApplicationScreeningRuns(id!), [id]);
  const attempts = useApi(() => getApplicationAttempts(id!), [id]);

  if (app.error) return <ErrorState error={app.error} onRetry={app.refetch} />;

  const handleScreen = async () => {
    setScreening(true);
    try {
      await screenApplication(id!);
      notify('success', 'Screening computed.');
      app.refetch();
      runs.refetch();
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Screening failed.');
    } finally {
      setScreening(false);
    }
  };

  const handleTransition = async () => {
    if (!targetStage || !currentActorId) return;
    setFormError(null);
    if (targetStage === 'Rejected' && !rejectedReason.trim()) {
      setFormError('A rejection reason is required.');
      return;
    }
    setTransitioning(true);
    try {
      await transitionApplication(id!, {
        to_stage: targetStage,
        actor_id: currentActorId,
        rejected_reason: targetStage === 'Rejected' ? rejectedReason.trim() : undefined,
      });
      notify('success', `Application moved to ${targetStage}.`);
      setTransitionOpen(false);
      setTargetStage('');
      setRejectedReason('');
      app.refetch();
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : 'Transition failed.');
    } finally {
      setTransitioning(false);
    }
  };

  const runColumns: Column<ScreeningRun>[] = [
    { key: 'id', header: 'Run', render: (r) => <span className={dashStyles.monoId}>{r.screening_run_id}</span> },
    { key: 'score', header: 'Score', render: (r) => r.screening_score.toFixed(2) },
    { key: 'decision', header: 'Decision', render: (r) => <StatusBadge status={r.screening_decision} /> },
    { key: 'version', header: 'Rule v.', render: (r) => r.screening_rule_version },
    { key: 'computed', header: 'Computed At', render: (r) => new Date(r.computed_at).toLocaleString() },
    { key: 'latest', header: 'Latest', render: (r) => <YesNoBadge value={r.is_latest} /> },
  ];

  const attemptColumns: Column<SubmissionAttempt>[] = [
    { key: 'id', header: 'Attempt', render: (a) => <span className={dashStyles.monoId}>{a.attempt_id}</span> },
    { key: 'submitted', header: 'Submitted At', render: (a) => new Date(a.submitted_at).toLocaleString() },
    { key: 'canonical', header: 'Canonical', render: (a) => <YesNoBadge value={a.is_canonical} /> },
    { key: 'issue', header: 'Issue Type', render: (a) => a.issue_type },
  ];

  const options = app.data ? NEXT_STAGE[app.data.stage] ?? [] : [];

  return (
    <div className={dashStyles.page}>
      <button className={styles.backLink} onClick={() => navigate('/screening')}>
        <ArrowLeft size={14} /> Back to screening
      </button>

      {app.loading || !app.data ? (
        <Card>
          <SkeletonRows rows={6} height={20} />
        </Card>
      ) : (
        <div className={styles.grid}>
          <div className={styles.mainCol}>
            <Card>
              <div className={styles.headerRow}>
                <div>
                  <h1 className={dashStyles.pageTitle}>{app.data.candidate_name ?? app.data.candidate_id}</h1>
                  <p className={dashStyles.pageSubtitle}>
                    Applying for {app.data.requisition_title ?? app.data.requisition_id}
                  </p>
                </div>
                <StatusBadge status={app.data.stage} />
              </div>

              <div className={styles.actionsRow}>
                <Button variant="secondary" size="sm" loading={screening} onClick={handleScreen}>
                  <PlayCircle size={14} /> Run Screening
                </Button>
                {options.length > 0 && (
                  <Button variant="primary" size="sm" onClick={() => setTransitionOpen(true)}>
                    Advance Stage
                  </Button>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader title="Screening Result" subtitle={app.data.screening_rule_version ? `Rule version ${app.data.screening_rule_version}` : undefined} />
              {app.data.screening_score === null ? (
                <p className={styles.noScore}>Not yet screened — run screening to compute a result.</p>
              ) : (
                <>
                  <div className={styles.decisionRow}>
                    <span className={styles.bigScore}>{app.data.screening_score.toFixed(2)}</span>
                    <StatusBadge status={app.data.screening_decision ?? 'Fail'} />
                  </div>
                  <ScoreBar label="Skill (50%)" value={app.data.screening_skill_component} />
                  <ScoreBar label="Experience (30%)" value={app.data.screening_experience_component} />
                  <ScoreBar label="Education (20%)" value={app.data.screening_education_component} />
                  <p className={styles.explanation}>{app.data.screening_explanation}</p>
                </>
              )}
            </Card>

            <Card padded={false}>
              <div style={{ padding: 20 }}>
                <CardHeader title="Screening History" subtitle={`${runs.data?.length ?? 0} run(s)`} />
              </div>
              {runs.loading ? (
                <div style={{ padding: '0 20px 20px' }}>
                  <SkeletonRows rows={2} height={32} />
                </div>
              ) : (
                <DataTable columns={runColumns} rows={runs.data ?? []} getRowKey={(r) => r.screening_run_id} emptyMessage="No screening runs yet." />
              )}
            </Card>

            <Card padded={false}>
              <div style={{ padding: 20 }}>
                <CardHeader title="Submission Attempts" subtitle="Every attempt ever logged for this candidate/requisition pair" />
              </div>
              {attempts.loading ? (
                <div style={{ padding: '0 20px 20px' }}>
                  <SkeletonRows rows={2} height={32} />
                </div>
              ) : (
                <DataTable columns={attemptColumns} rows={attempts.data ?? []} getRowKey={(a) => a.attempt_id} emptyMessage="No attempts on file." />
              )}
            </Card>
          </div>

          <div className={styles.sideCol}>
            <Card>
              <CardHeader title="Candidate Profile" />
              {candidate.loading ? (
                <SkeletonRows rows={4} height={18} />
              ) : candidate.data ? (
                <div className={styles.profile}>
                  <div className={styles.profileRow}>
                    <Mail size={14} /> {candidate.data.email}
                  </div>
                  {candidate.data.phone && (
                    <div className={styles.profileRow}>
                      <Phone size={14} /> {candidate.data.phone}
                    </div>
                  )}
                  <div className={styles.profileRow}>
                    <MapPin size={14} /> {candidate.data.location_city}, {candidate.data.location_country}
                  </div>
                  <div className={styles.profileFact}>
                    <span>Experience</span>
                    <strong>{candidate.data.years_experience} yrs</strong>
                  </div>
                  <div className={styles.profileFact}>
                    <span>Education</span>
                    <strong>{candidate.data.highest_education_level}</strong>
                  </div>
                  <div className={styles.profileFact}>
                    <span>Source</span>
                    <strong>{candidate.data.source_channel}</strong>
                  </div>
                </div>
              ) : null}
            </Card>

            <Card>
              <CardHeader title="Skills" />
              {skills.loading ? (
                <SkeletonRows rows={3} height={16} />
              ) : (skills.data?.length ?? 0) === 0 ? (
                <p className={styles.noScore}>No skills on file.</p>
              ) : (
                <div className={styles.skillList}>
                  {skills.data!.map((s) => (
                    <div key={s.skill_id} className={styles.skillChip}>
                      {s.skill_name} <span className={styles.skillLevel}>{s.proficiency_level}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Resume" />
              {resumes.loading ? (
                <SkeletonRows rows={2} height={16} />
              ) : (resumes.data?.length ?? 0) === 0 ? (
                <p className={styles.noScore}>No resume on file.</p>
              ) : (
                resumes.data!.filter((r) => r.is_latest).map((r) => (
                  <div key={r.resume_artifact_id} className={styles.profileFact}>
                    <span>{r.file_name}</span>
                    <strong>{r.parsed_years_experience}y / {r.parsed_education_level}</strong>
                  </div>
                ))
              )}
            </Card>
          </div>
        </div>
      )}

      <Dialog
        open={transitionOpen}
        onClose={() => setTransitionOpen(false)}
        title="Advance Application Stage"
        footer={
          <>
            <Button variant="ghost" onClick={() => setTransitionOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={transitioning} disabled={!targetStage} onClick={handleTransition}>
              Confirm
            </Button>
          </>
        }
      >
        <FormField label="New stage" required>
          <Select value={targetStage} onChange={(e) => setTargetStage(e.target.value as ApplicationStage)}>
            <option value="">Select a stage…</option>
            {options.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </FormField>
        {targetStage === 'Rejected' && (
          <FormField label="Rejection reason" required error={formError ?? undefined}>
            <Input value={rejectedReason} onChange={(e) => setRejectedReason(e.target.value)} placeholder="e.g. Did not meet experience bar" invalid={!!formError} />
          </FormField>
        )}
      </Dialog>
    </div>
  );
}
