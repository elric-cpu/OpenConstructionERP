export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatBytes(value: number): string {
  return value < 1_000_000 ? `${Math.ceil(value / 1_000)} KB` : `${(value / 1_000_000).toFixed(1)} MB`;
}

export function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
