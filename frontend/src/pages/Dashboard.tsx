import { Briefcase, Users, Target, HandCoins, ShieldAlert, Download } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { getAnomalySummary, getFunnelReport } from '../api/resources';
import { API_BASE } from '../api/client';
import { Card, CardHeader, KPICard } from '../components/Card';
import { ErrorState, SkeletonRows } from '../components/States';
import { Button } from '../components/Button';
import { FunnelChart } from '../charts/FunnelChart';
import { StatusDonut } from '../charts/StatusDonut';
import { AnomalyBarChart } from '../charts/AnomalyBarChart';
import styles from './Dashboard.module.css';

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(0)}%`;
}

export default function Dashboard() {
  const funnel = useApi(getFunnelReport, []);
  const anomalies = useApi(getAnomalySummary, []);

  const loading = funnel.loading || anomalies.loading;
  const error = funnel.error ?? anomalies.error;

  if (error) {
    return <ErrorState error={error} onRetry={() => { funnel.refetch(); anomalies.refetch(); }} />;
  }

  const overall = funnel.data?.requisition_funnel_overall[0];
  const openCount = funnel.data?.requisition_status_distribution.find((r) => r.status === 'Open')?.count ?? 0;
  const totalRequisitions = funnel.data?.requisition_status_distribution.reduce((s, r) => s + r.count, 0) ?? 0;
  const acceptance = funnel.data?.offer_acceptance_rate_overall[0];
  const scheduledInterviews = funnel.data?.interviewer_load.reduce((s, r) => s + r.interview_count, 0) ?? 0;

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Executive Dashboard</h1>
          <p className={styles.pageSubtitle}>Live recruitment operations across every requisition and candidate.</p>
        </div>
        <div className={styles.exportButtons}>
          <a href={`${API_BASE}/api/v1/exports/funnel.json`}>
            <Button size="sm" variant="secondary">
              <Download size={14} /> Funnel report
            </Button>
          </a>
          <a href={`${API_BASE}/api/v1/exports/anomaly-summary.json`}>
            <Button size="sm" variant="secondary">
              <Download size={14} /> Anomaly report
            </Button>
          </a>
        </div>
      </div>

      {loading ? (
        <div className={styles.kpiGrid}>
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}>
              <SkeletonRows rows={3} height={18} />
            </Card>
          ))}
        </div>
      ) : (
        <div className={styles.kpiGrid}>
          <KPICard
            label="Open Requisitions"
            value={String(openCount)}
            context={`${totalRequisitions} total`}
            icon={<Briefcase size={16} />}
          />
          <KPICard
            label="Applications"
            value={String(overall?.reached_counts.Applied ?? 0)}
            context={`${overall?.reached_counts.Hired ?? 0} hired`}
            tone="success"
            icon={<Users size={16} />}
          />
          <KPICard
            label="Screening Pass Rate"
            value={pct(overall?.conversion_rates['Screening->Interviewing'])}
            context="of screened applications advance"
            tone="neutral"
            icon={<Target size={16} />}
          />
          <KPICard
            label="Offer Acceptance Rate"
            value={pct(acceptance?.acceptance_rate)}
            context={`${acceptance?.accepted_count ?? 0} of ${acceptance?.extended_count ?? 0} extended`}
            tone="success"
            icon={<HandCoins size={16} />}
          />
          <KPICard
            label="Active Anomalies"
            value={String(anomalies.data?.total_violations ?? 0)}
            context="detected by live validation"
            tone={(anomalies.data?.total_violations ?? 0) > 0 ? 'warning' : 'success'}
            icon={<ShieldAlert size={16} />}
          />
        </div>
      )}

      <div className={styles.chartsGrid}>
        <Card>
          <CardHeader title="Recruitment Funnel" subtitle="Applications reaching each stage, Applied → Hired" />
          {loading ? (
            <SkeletonRows rows={5} height={32} />
          ) : overall ? (
            <FunnelChart row={overall} />
          ) : (
            <p className={styles.noData}>No applications yet.</p>
          )}
        </Card>

        <Card>
          <CardHeader title="Requisition Status" subtitle="Distribution across the lifecycle" />
          {loading ? (
            <SkeletonRows rows={5} height={24} />
          ) : (
            <StatusDonut data={funnel.data?.requisition_status_distribution ?? []} />
          )}
        </Card>

        <Card>
          <CardHeader title="Operational Anomalies" subtitle="Live detection, counted by type — not seeded ground truth" />
          {loading ? (
            <SkeletonRows rows={5} height={24} />
          ) : (anomalies.data?.total_violations ?? 0) > 0 ? (
            <AnomalyBarChart counts={anomalies.data!.counts_by_anomaly_type} />
          ) : (
            <p className={styles.noData}>No anomalies currently detected.</p>
          )}
        </Card>

        <Card>
          <CardHeader title="Pipeline Velocity" subtitle="Mean days spent in each stage" />
          {loading ? (
            <SkeletonRows rows={5} height={20} />
          ) : (
            <div className={styles.velocityList}>
              {Object.entries(funnel.data?.time_in_stage ?? {}).map(([stage, stats]) => (
                <div key={stage} className={styles.velocityRow}>
                  <span className={styles.velocityStage}>{stage}</span>
                  <div className={styles.velocityBarTrack}>
                    <div
                      className={styles.velocityBarFill}
                      style={{ width: `${Math.min(100, (stats.mean_days / 14) * 100)}%` }}
                    />
                  </div>
                  <span className={styles.velocityValue}>{stats.mean_days.toFixed(1)}d</span>
                </div>
              ))}
              {Object.keys(funnel.data?.time_in_stage ?? {}).length === 0 && (
                <p className={styles.noData}>Not enough stage history yet.</p>
              )}
            </div>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Scheduled Interviews"
          subtitle={`${scheduledInterviews} interviews across ${funnel.data?.interviewer_load.length ?? 0} interviewer/week combinations`}
        />
        <p className={styles.noData}>
          See Interview Management for interviewer-level availability and scheduling detail.
        </p>
      </Card>
    </div>
  );
}
