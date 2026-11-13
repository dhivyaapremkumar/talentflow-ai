import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { FunnelGroupRow } from '../types/api';

const STAGE_COLORS: Record<string, string> = {
  Applied: '#94a3b8',
  Screening: '#60a5fa',
  Interviewing: '#38bdf8',
  Offer: '#f59e0b',
  Hired: '#10b981',
};

export function FunnelChart({ row }: { row: FunnelGroupRow }) {
  const data = Object.entries(row.reached_counts).map(([stage, count]) => ({ stage, count }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} layout="vertical" margin={{ left: 24, right: 24, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e3e7ed" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 12, fill: '#64748b' }} axisLine={false} tickLine={false} />
        <YAxis
          type="category"
          dataKey="stage"
          width={90}
          tick={{ fontSize: 12, fill: '#1e293b', fontWeight: 600 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          formatter={(value) => [String(value), 'Applications']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e3e7ed', fontSize: 13 }}
        />
        <Bar dataKey="count" radius={[0, 6, 6, 0]} maxBarSize={28}>
          {data.map((d) => (
            <Cell key={d.stage} fill={STAGE_COLORS[d.stage] ?? '#94a3b8'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
