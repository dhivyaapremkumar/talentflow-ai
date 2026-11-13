import type { ReactNode } from 'react';
import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';
import type { ApiError } from '../api/client';
import { Button } from './Button';
import styles from './States.module.css';

export function Skeleton({ height = 16, width = '100%' }: { height?: number; width?: string | number }) {
  return <div className={styles.skeleton} style={{ height, width }} />;
}

export function SkeletonRows({ rows = 5, height = 44 }: { rows?: number; height?: number }) {
  return (
    <div className={styles.skeletonStack}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} height={height} />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>{icon ?? <Inbox size={22} />}</div>
      <p className={styles.emptyTitle}>{title}</p>
      {description && <p className={styles.emptyDesc}>{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className={styles.error}>
      <div className={styles.errorIcon}>
        <AlertTriangle size={20} />
      </div>
      <div className={styles.errorBody}>
        <p className={styles.errorTitle}>Could not load this data</p>
        <p className={styles.errorMessage}>
          {error.message}
          {error.code !== 'unknown_error' && <span className={styles.errorCode}> ({error.code})</span>}
        </p>
      </div>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          <RefreshCw size={14} /> Retry
        </Button>
      )}
    </div>
  );
}

export function InlineBanner({ tone, children }: { tone: 'success' | 'error'; children: ReactNode }) {
  return <div className={`${styles.banner} ${styles[tone]}`}>{children}</div>;
}
