import styles from './Badge.module.css';

export type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'navy';

const STATUS_TONE: Record<string, BadgeTone> = {
  // Requisition
  Draft: 'neutral',
  PendingApproval: 'warning',
  Approved: 'info',
  Open: 'success',
  OnHold: 'warning',
  Closed: 'neutral',
  Cancelled: 'danger',
  // Application
  Applied: 'neutral',
  Screening: 'info',
  Interviewing: 'info',
  Offer: 'warning',
  Hired: 'success',
  Rejected: 'danger',
  Withdrawn: 'neutral',
  // Interview
  Scheduled: 'info',
  Completed: 'success',
  NoShow: 'danger',
  // Offer
  Drafted: 'neutral',
  Extended: 'warning',
  Accepted: 'success',
  Declined: 'danger',
  Rescinded: 'danger',
  Expired: 'neutral',
  // Screening decision
  Pass: 'success',
  Fail: 'danger',
};

export function toneForStatus(status: string): BadgeTone {
  return STATUS_TONE[status] ?? 'neutral';
}

export function Badge({ tone = 'neutral', children }: { tone?: BadgeTone; children: React.ReactNode }) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={toneForStatus(status)}>{status}</Badge>;
}

export function YesNoBadge({ value, yesLabel = 'Yes', noLabel = 'No' }: { value: boolean; yesLabel?: string; noLabel?: string }) {
  return <Badge tone={value ? 'success' : 'neutral'}>{value ? yesLabel : noLabel}</Badge>;
}
