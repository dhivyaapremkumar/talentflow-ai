import type { ReactNode } from 'react';
import styles from './Card.module.css';

export function Card({ children, className, padded = true }: { children: ReactNode; className?: string; padded?: boolean }) {
  return <div className={[styles.card, padded ? styles.padded : '', className].filter(Boolean).join(' ')}>{children}</div>;
}

export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className={styles.header}>
      <div>
        <h3 className={styles.title}>{title}</h3>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function KPICard({
  label,
  value,
  context,
  tone = 'neutral',
  icon,
}: {
  label: string;
  value: string;
  context?: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
  icon?: ReactNode;
}) {
  return (
    <div className={styles.kpi}>
      <div className={styles.kpiTop}>
        <span className={styles.kpiLabel}>{label}</span>
        {icon && <span className={`${styles.kpiIcon} ${styles[`icon_${tone}`]}`}>{icon}</span>}
      </div>
      <div className={styles.kpiValue}>{value}</div>
      {context && <div className={`${styles.kpiContext} ${styles[tone]}`}>{context}</div>}
    </div>
  );
}
