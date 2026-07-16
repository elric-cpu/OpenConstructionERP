import { ClipboardCheck, ShieldAlert } from "lucide-react";
import { Empty, Panel } from "./SharedUi";
import type { Lead, SpamFilter } from "./types";

export function LeadQueue({
  leads,
  sourceFilter,
  spamFilter,
  statusFilter,
  onOpen,
  setSourceFilter,
  setSpamFilter,
  setStatusFilter,
}: {
  leads: Lead[];
  sourceFilter: string;
  spamFilter: SpamFilter;
  statusFilter: string;
  onOpen(leadId: string): void;
  setSourceFilter(value: string): void;
  setSpamFilter(value: SpamFilter): void;
  setStatusFilter(value: string): void;
}) {
  const sources = [...new Set(leads.map((lead) => lead.source))].sort();
  return (
    <Panel title="Lead queue" subtitle="Website requests and staff follow-up." link="Live">
      <div className="queue-tools">
        <label>
          Status
          <select
            aria-label="Filter leads by status"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">All statuses</option>
            {["new", "contacted", "qualified", "scheduled", "closed"].map((status) => (
              <option key={status}>{status}</option>
            ))}
          </select>
        </label>
        <label>
          Source
          <select
            aria-label="Filter leads by source"
            value={sourceFilter}
            onChange={(event) => setSourceFilter(event.target.value)}
          >
            <option value="">All sources</option>
            {sources.map((source) => (
              <option key={source}>{source}</option>
            ))}
          </select>
        </label>
        <label>
          Queue
          <select
            aria-label="Filter spam leads"
            value={spamFilter}
            onChange={(event) => setSpamFilter(event.target.value as SpamFilter)}
          >
            <option value="active">Active leads</option>
            <option value="spam">Spam</option>
            <option value="all">All leads</option>
          </select>
        </label>
        <span>{leads.length} shown</span>
      </div>
      {leads.length ? (
        <div className="lead-list">
          {leads.map((lead) => (
            <button className="lead-row" key={lead.id} onClick={() => onOpen(lead.id)}>
              <span className={lead.priority === "urgent" ? "priority urgent" : "priority"}>{lead.priority}</span>
              <div>
                <strong>{lead.name}</strong>
                <small>
                  {lead.service_type} · {lead.city || "Location pending"}
                </small>
                <small className="lead-source">Source: {lead.source}</small>
              </div>
              <time>
                {new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(new Date(lead.created_at))}
              </time>
              <span className="lead-status">{lead.status}</span>
              {lead.is_spam && (
                <span className="spam-flag">
                  <ShieldAlert /> Spam
                </span>
              )}
            </button>
          ))}
        </div>
      ) : (
        <Empty icon={<ClipboardCheck />} title="You’re caught up" body="New website requests will appear here." />
      )}
    </Panel>
  );
}
