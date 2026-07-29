import { History } from "lucide-react";
import { formatDate } from "./formatters";
import type { AuditEvent } from "./types";

export function LeadAuditPanel({ events }: { events: AuditEvent[] }) {
  return (
    <section className="workspace-card audit-card">
      <div className="card-heading">
        <div>
          <small>IMMUTABLE HISTORY</small>
          <h2>Audit trail</h2>
        </div>
        <History />
      </div>
      <ol>
        {events.map((event) => (
          <li key={event.id}>
            <strong>{event.event.replaceAll(".", " ")}</strong>
            <span>{event.actor}</span>
            <time>{formatDate(event.occurred_at)}</time>
          </li>
        ))}
      </ol>
    </section>
  );
}
