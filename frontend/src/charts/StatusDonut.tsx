import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { RequisitionStatusDistributionRow } from '../types/api';

const COLORS: Record<string, string> = {
  Draft: '#cbd5e1',
  PendingApproval: '#f59e0b',
  Approved: '#60a5fa',
  Open: '#10b981',
  OnHold: '#fbbf24',
  Closed: '#94a3b8',
  Cancelled: '#ef4444',
};

export function StatusDonut({ data }: { data: RequisitionStatusDistributionRow[] }) {
  if (data.length === 0) return null;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="status"
          innerRadius={55}
          outerRadius={85}
          paddingAngle={2}
          stroke="none"
        >
          {data.map((d) => (
            <Cell key={d.status} fill={COLORS[d.status] ?? '#94a3b8'} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e3e7ed', fontSize: 13 }} />
        <Legend
          verticalAlign="middle"
          layout="vertical"
          align="right"
          iconType="circle"
          iconSize={8}
          formatter={(value: string) => <span style={{ fontSize: 12, color: '#334155' }}>{value}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
