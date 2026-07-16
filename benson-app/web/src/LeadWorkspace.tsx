import { useEffect, useState } from "react";
import { ArrowLeft, Download, FileText, History, LoaderCircle, Send, Sparkles, UserRound } from "lucide-react";

export type Lead = {
  id: string;
  status: string;
  priority: string;
  name: string;
  phone: string;
  email: string | null;
  service_type: string;
  city: string;
  created_at: string;
  assigned_to: string | null;
};

type Attachment = {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

type Note = { id: string; author: string; body: string; created_at: string };
type AuditEvent = {
  id: string;
  event: string;
  actor: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

type LeadDetail = Lead & {
  payload: Record<string, unknown>;
  attachments: Attachment[];
  notes: Note[];
  audit_events: AuditEvent[];
};

type Skill = { id: string; label: string; description: string; risk: string };
type StaffMember = { email: string; display_name: string; role: string };

const transitions: Record<string, string[]> = {
  new: ["contacted", "closed"],
  contacted: ["qualified", "closed"],
  qualified: ["scheduled", "closed"],
  scheduled: ["closed"],
  closed: [],
};

async function api<T>(url: string, credential: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      authorization: `Bearer ${credential}`,
      ...(init?.body ? { "content-type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) throw new Error((await response.text()) || "Operations request failed");
  return response.json() as Promise<T>;
}

export function LeadWorkspace({
  leadId,
  credential,
  onBack,
  onChanged,
}: {
  leadId: string;
  credential: string;
  onBack(): void;
  onChanged(lead: Lead): void;
}) {
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [skillId, setSkillId] = useState("historical-cost-analyzer");
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState("");
  const [prompt, setPrompt] = useState("Summarize this lead and draft the next three staff actions.");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<"lead" | "save" | "draft" | "">("lead");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setBusy("lead");
    setError("");
    Promise.all([
      api<LeadDetail>(`/api/benson/v1/leads/${leadId}`, credential, { signal: controller.signal }),
      api<{ skills: Skill[] }>("/api/benson/v1/ai/skills", credential, { signal: controller.signal }),
      api<{ staff: StaffMember[] }>("/api/benson/v1/staff", credential, { signal: controller.signal }),
    ])
      .then(([detail, catalog, directory]) => {
        if (!active) return;
        setLead(detail);
        setAssignee(detail.assigned_to ?? "");
        setSkills(catalog.skills);
        setStaff(directory.staff);
        setSkillId((current) =>
          catalog.skills.some((skill) => skill.id === current) ? current : (catalog.skills[0]?.id ?? ""),
        );
      })
      .catch((error) => {
        if (active && error instanceof Error && error.name !== "AbortError")
          setError("Lead details could not be loaded.");
      })
      .finally(() => {
        if (active) setBusy("");
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [credential, leadId]);

  const save = async (change: Record<string, string>) => {
    setBusy("save");
    setError("");
    try {
      const updated = await api<LeadDetail>(`/api/benson/v1/leads/${leadId}`, credential, {
        method: "PATCH",
        body: JSON.stringify(change),
      });
      setLead(updated);
      setAssignee(updated.assigned_to ?? "");
      setNote("");
      onChanged(updated);
    } catch {
      setError("The lead change was not saved. Review the values and try again.");
    } finally {
      setBusy("");
    }
  };

  const runDraft = async () => {
    if (!lead || !prompt.trim()) return;
    setBusy("draft");
    setDraft("");
    setError("");
    try {
      const result = await api<{ summary: string; status: string }>("/api/benson/v1/ai/runs", credential, {
        method: "POST",
        body: JSON.stringify({
          skill_id: skillId,
          prompt,
          lead_id: lead.id,
        }),
      });
      setDraft(result.summary);
    } catch {
      setError("The Benson Assistant is unavailable. No lead data was changed.");
    } finally {
      setBusy("");
    }
  };

  const download = async (attachment: Attachment) => {
    setError("");
    try {
      const response = await fetch(`/api/benson/v1/attachments/${attachment.id}`, {
        headers: { authorization: `Bearer ${credential}` },
      });
      if (!response.ok) throw new Error("download failed");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = attachment.original_name;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("The private attachment could not be downloaded.");
    }
  };

  if (busy === "lead") {
    return (
      <section className="lead-workspace loading-state" aria-live="polite">
        <LoaderCircle className="spin" /> Loading lead workspace…
      </section>
    );
  }
  if (!lead) {
    return (
      <section className="lead-workspace">
        <button className="text-button" onClick={onBack}>
          <ArrowLeft /> Back to leads
        </button>
        <p className="form-error">{error || "Lead not found."}</p>
      </section>
    );
  }

  const intake = lead.payload;
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
            {lead.service_type} · {lead.city || "Location pending"} · received {formatDate(lead.created_at)}
          </p>
        </div>
        <a className="primary" href={`tel:${lead.phone}`}>
          Call {lead.phone}
        </a>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <div className="lead-columns">
        <div className="lead-main">
          <section className="workspace-card intake-card">
            <div className="card-heading">
              <div>
                <small>REQUEST</small>
                <h2>Homeowner details</h2>
              </div>
              <FileText />
            </div>
            <dl className="intake-grid">
              <Detail label="Email" value={lead.email} />
              <Detail label="Phone" value={lead.phone} />
              <Detail label="Address" value={stringValue(intake.address)} />
              <Detail label="Timeline" value={stringValue(intake.timeline)} />
              <Detail label="Request" value={stringValue(intake.message)} wide />
              <Detail label="Access notes" value={stringValue(intake.access_notes)} wide />
            </dl>
          </section>

          <section className="workspace-card">
            <div className="card-heading">
              <div>
                <small>PRIVATE FILES</small>
                <h2>Attachments</h2>
              </div>
              <Download />
            </div>
            {lead.attachments.length ? (
              <div className="attachment-list">
                {lead.attachments.map((attachment) => (
                  <button key={attachment.id} onClick={() => download(attachment)}>
                    <FileText />
                    <span>
                      <strong>{attachment.original_name}</strong>
                      <small>
                        {attachment.content_type} · {formatBytes(attachment.size_bytes)}
                      </small>
                    </span>
                    <Download />
                  </button>
                ))}
              </div>
            ) : (
              <p className="quiet">No customer files are attached.</p>
            )}
          </section>

          <section className="workspace-card">
            <div className="card-heading">
              <div>
                <small>STAFF RECORD</small>
                <h2>Notes</h2>
              </div>
              <UserRound />
            </div>
            <form
              className="note-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (note.trim()) void save({ note });
              }}
            >
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Add a factual call note, measurement, or next step…"
                aria-label="New lead note"
              />
              <button className="primary" disabled={!note.trim() || busy === "save"}>
                {busy === "save" ? "Saving…" : "Add note"}
              </button>
            </form>
            <div className="note-list">
              {lead.notes.map((item) => (
                <article key={item.id}>
                  <p>{item.body}</p>
                  <small>
                    {item.author} · {formatDate(item.created_at)}
                  </small>
                </article>
              ))}
              {!lead.notes.length && <p className="quiet">No staff notes yet.</p>}
            </div>
          </section>
        </div>

        <div className="lead-side">
          <section className="workspace-card workflow-card">
            <small>WORKFLOW</small>
            <h2>Ownership</h2>
            <label>
              Status
              <select value={lead.status} onChange={(event) => void save({ status: event.target.value })}>
                {[lead.status, ...(transitions[lead.status] ?? [])].map((status) => (
                  <option key={status}>{status}</option>
                ))}
              </select>
            </label>
            <label>
              Assigned to
              <select
                aria-label="Assigned to"
                value={assignee}
                onChange={(event) => setAssignee(event.target.value)}
              >
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
              disabled={!assignee || assignee === lead.assigned_to || busy === "save"}
              onClick={() => void save({ assigned_to: assignee })}
            >
              Save assignment
            </button>
          </section>

          <section className="workspace-card lead-agent">
            <div className="agent-head">
              <Sparkles />
              <div>
                <small>LEAD-SCOPED AI</small>
                <h2>Benson Assistant</h2>
              </div>
            </div>
            <p>Drafts use only this lead’s supplied facts. No record or message is changed without staff action.</p>
            <label>
              Reviewed skill
              <select value={skillId} onChange={(event) => setSkillId(event.target.value)}>
                {skills.map((skill) => (
                  <option key={skill.id} value={skill.id}>
                    {skill.label}
                  </option>
                ))}
              </select>
            </label>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              aria-label="Lead assistant prompt"
            />
            <button
              className="agent-button"
              disabled={busy === "draft" || !prompt.trim()}
              onClick={() => void runDraft()}
            >
              {busy === "draft" ? (
                <>
                  <LoaderCircle className="spin" /> Drafting…
                </>
              ) : (
                <>
                  <Send /> Create draft
                </>
              )}
            </button>
            {draft && (
              <div className="draft-output">
                <small>REVIEWABLE DRAFT</small>
                <p>{draft}</p>
              </div>
            )}
          </section>

          <section className="workspace-card audit-card">
            <div className="card-heading">
              <div>
                <small>IMMUTABLE HISTORY</small>
                <h2>Audit trail</h2>
              </div>
              <History />
            </div>
            <ol>
              {lead.audit_events.map((event) => (
                <li key={event.id}>
                  <strong>{event.event.replaceAll(".", " ")}</strong>
                  <span>{event.actor}</span>
                  <time>{formatDate(event.occurred_at)}</time>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </section>
  );
}

function Detail({ label, value, wide = false }: { label: string; value: string | null; wide?: boolean }) {
  return (
    <div className={wide ? "wide" : ""}>
      <dt>{label}</dt>
      <dd>{value || "Not provided"}</dd>
    </div>
  );
}
function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}
function formatBytes(value: number): string {
  return value < 1_000_000 ? `${Math.ceil(value / 1_000)} KB` : `${(value / 1_000_000).toFixed(1)} MB`;
}
