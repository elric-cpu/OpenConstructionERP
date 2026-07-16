import { ArrowLeft, LoaderCircle } from "lucide-react";
import { formatDate } from "./formatters";
import { LeadAssistantPanel } from "./LeadAssistantPanel";
import { LeadAttachmentsPanel } from "./LeadAttachmentsPanel";
import { LeadAuditPanel } from "./LeadAuditPanel";
import { LeadDetailsPanel } from "./LeadDetailsPanel";
import { LeadNotesPanel } from "./LeadNotesPanel";
import { LeadWorkflowPanel } from "./LeadWorkflowPanel";
import type { Lead } from "./types";
import { useLeadWorkspace } from "./useLeadWorkspace";

export type { Lead } from "./types";

export function LeadWorkspace({
  leadId,
  credential,
  onBack,
  onChanged,
  onDeleted,
}: {
  leadId: string;
  credential: string;
  onBack(): void;
  onChanged(lead: Lead): void;
  onDeleted(leadId: string): void;
}) {
  const workspace = useLeadWorkspace({ credential, leadId, onChanged, onDeleted });
  if (workspace.busy === "lead") {
    return (
      <section className="lead-workspace loading-state" aria-live="polite">
        <LoaderCircle className="spin" /> Loading lead workspace…
      </section>
    );
  }
  if (!workspace.lead) {
    return (
      <section className="lead-workspace">
        <button className="text-button" onClick={onBack}>
          <ArrowLeft /> Back to leads
        </button>
        <p className="form-error">{workspace.error || "Lead not found."}</p>
      </section>
    );
  }
  const lead = workspace.lead;
  return (
    <section className="lead-workspace" aria-label={`${lead.name} lead workspace`}>
      <div className="lead-workspace-head">
        <button className="text-button" onClick={onBack}>
          <ArrowLeft /> Lead queue
        </button>
        <div>
          <span className={`priority ${lead.priority === "urgent" ? "urgent" : ""}`}>{lead.priority}</span>
          <h1>{lead.name}</h1>
          <p>
            {lead.service_type} · {lead.city || "Location pending"} · source {lead.source} · received{" "}
            {formatDate(lead.created_at)}
          </p>
        </div>
        <a className="primary" href={`tel:${lead.phone}`}>
          Call {lead.phone}
        </a>
      </div>
      {workspace.error && (
        <p className="form-error" role="alert">
          {workspace.error}
        </p>
      )}
      <div className="lead-columns">
        <div className="lead-main">
          <LeadDetailsPanel
            busy={workspace.busy === "save"}
            edit={workspace.edit}
            lead={lead}
            save={(change) => void workspace.save(change)}
            setEdit={workspace.setEdit}
          />
          <LeadAttachmentsPanel attachments={lead.attachments} credential={credential} onError={workspace.setError} />
          <LeadNotesPanel
            busy={workspace.busy === "save"}
            note={workspace.note}
            notes={lead.notes}
            save={(change) => void workspace.save(change)}
            setNote={workspace.setNote}
          />
        </div>
        <div className="lead-side">
          <LeadWorkflowPanel
            assignee={workspace.assignee}
            busy={workspace.busy === "save"}
            lead={lead}
            staff={workspace.staff}
            deleteLead={() => void workspace.deleteLead()}
            save={(change) => void workspace.save(change)}
            setAssignee={workspace.setAssignee}
          />
          <LeadAssistantPanel
            busy={workspace.busy === "draft"}
            draft={workspace.draft}
            prompt={workspace.prompt}
            skillId={workspace.skillId}
            skills={workspace.skills}
            runDraft={() => void workspace.runDraft()}
            setPrompt={workspace.setPrompt}
            setSkillId={workspace.setSkillId}
          />
          <LeadAuditPanel events={lead.audit_events} />
        </div>
      </div>
    </section>
  );
}
