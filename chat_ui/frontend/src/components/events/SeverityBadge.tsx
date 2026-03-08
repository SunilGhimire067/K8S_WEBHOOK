interface Props {
  severity: string;
}

export function SeverityBadge({ severity }: Props) {
  const s = severity?.toLowerCase() || "info";
  return <span className={`severity-badge ${s}`}>{s.toUpperCase()}</span>;
}
