import { ShieldAlert, Trash2 } from "lucide-react";
import type { LeadDetail, StaffMember } from "./types";

const transitions: Record<string, string[]> = {
  new: ["contacted", "closed"],
  contacted: ["qualified", "closed"],
  qualified: ["scheduled", "closed"],
  scheduled: ["closed"],
  closed: [],
};

export function LeadWorkflowPanel({
  assignee,
  busy,
  lead,
  staff,
  deleteLead,
  save,
  setAssignee,
}: {
  assignee: string;
  busy: boolean;
  lead: LeadDetail;
  staff: StaffMember[];
  deleteLead(): void;
  save(change: Record<string, string | boolean>): void;
  setAssignee(value: string): void;
}) {
  return (
    <section className="workspace-card workflow-card">
      <small>WORKFLOW</small>
      <h2>Ownership</h2>
      <label>
        Status
        <select value={lead.status} onChange={(event) => save({ status: event.target.value })}>
          {[lead.status, ...(transitions[lead.status] ?? [])].map((status) => (
            <option key={status}>{status}</option>
          ))}
        </select>
      </label>
      <label>
        Assigned to
        <select aria-label="Assigned to" value={assignee} onChange={(event) => setAssignee(event.target.value)}>
          <option value="">Unassigned</option>
          {lead.assigned_to && !staff.some((member) => member.email === lead.assigned_to) && (
            <option value={lead.assigned_to}>{lead.assigned_to}</option>
          )}
          {staff.map((member) => (
            <option key={member.email} value={member.email}>
              {member.display_name}
            </option>
          ))}
        </select>
      </label>
      <button
        className="secondary"
        disabled={!assignee || assignee === lead.assigned_to || busy}
        onClick={() => save({ assigned_to: assignee })}
      >
        Save assignment
      </button>
      <div className="record-actions">
        <button className="secondary" onClick={() => save({ is_spam: !lead.is_spam })}>
          <ShieldAlert /> {lead.is_spam ? "Not spam" : "Mark as spam"}
        </button>
        {lead.is_spam && <small>{lead.spam_reason || "Flagged by staff"}</small>}
        <button className="danger-button" onClick={deleteLead}>
          <Trash2 /> Delete lead
        </button>
      </div>
    </section>
  );
}
