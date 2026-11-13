import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export function AnomalyBarChart({ counts }: { counts: Record<string, number> }) {
  const data = Object.entries(counts).map(([type, count]) => ({
    type: type.replace(/([A-Z])/g, ' $1').trim(),
    count,
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 32 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e3e7ed" vertical={false} />
        <XAxis
          dataKey="type"
          tick={{ fontSize: 11, fill: '#64748b' }}
          angle={-20}
          textAnchor="end"
          interval={0}
          axisLine={false}
          tickLine={false}
          height={50}
        />
        <YAxis tick={{ fontSize: 12, fill: '#64748b' }} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e3e7ed', fontSize: 13 }} />
        <Bar dataKey="count" fill="#f59e0b" radius={[6, 6, 0, 0]} maxBarSize={48} />
      </BarChart>
    </ResponsiveContainer>
  );
}
