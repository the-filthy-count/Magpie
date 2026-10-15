export default function Stat({
  label,
  value,
  icon,
  foot,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  foot: string;
}) {
  return (
    <div className="stat-card">
      <div>
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      <small>{foot}</small>
    </div>
  );
}
