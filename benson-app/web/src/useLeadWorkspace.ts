import { useEffect, useState } from "react";
import { operationsApi } from "./api";
import type { BusyState, EditableLead, Lead, LeadDetail, Skill, StaffMember } from "./types";

const blankEdit: EditableLead = { name: "", phone: "", email: "", service_type: "", city: "", source: "" };
const defaultPrompt = "Summarize this lead and draft the next three staff actions.";

function editableFrom(lead: LeadDetail): EditableLead {
  return {
    name: lead.name,
    phone: lead.phone,
    email: lead.email ?? "",
    service_type: lead.service_type,
    city: lead.city,
    source: lead.source,
  };
}

export function useLeadWorkspace({
  credential,
  leadId,
  onChanged,
  onDeleted,
}: {
  credential: string;
  leadId: string;
  onChanged(lead: Lead): void;
  onDeleted(leadId: string): void;
}) {
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [skillId, setSkillId] = useState("historical-cost-analyzer");
  const [assignee, setAssignee] = useState("");
  const [edit, setEdit] = useState(blankEdit);
  const [note, setNote] = useState("");
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<BusyState>("lead");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setBusy("lead");
    setError("");
    Promise.all([
      operationsApi<LeadDetail>(`/api/benson/v1/leads/${leadId}`, credential, { signal: controller.signal }),
      operationsApi<{ skills: Skill[] }>("/api/benson/v1/ai/skills", credential, { signal: controller.signal }),
      operationsApi<{ staff: StaffMember[] }>("/api/benson/v1/staff", credential, { signal: controller.signal }),
    ])
      .then(([detail, catalog, directory]) => {
        if (!active) return;
        setLead(detail);
        setAssignee(detail.assigned_to ?? "");
        setEdit(editableFrom(detail));
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

  const save = async (change: Record<string, string | boolean>) => {
    setBusy("save");
    setError("");
    try {
      const updated = await operationsApi<LeadDetail>(`/api/benson/v1/leads/${leadId}`, credential, {
        method: "PATCH",
        body: JSON.stringify(change),
      });
      setLead(updated);
      setAssignee(updated.assigned_to ?? "");
      setEdit(editableFrom(updated));
      setNote("");
      onChanged(updated);
    } catch {
      setError("The lead change was not saved. Review the values and try again.");
    } finally {
      setBusy("");
    }
  };
  const deleteLead = async () => {
    if (
      !lead ||
      !window.confirm(`Delete ${lead.name}? The lead will be removed from the queue but retained for audit.`)
    )
      return;
    setBusy("save");
    setError("");
    try {
      const response = await fetch(`/api/benson/v1/leads/${lead.id}`, {
        method: "DELETE",
        headers: { authorization: `Bearer ${credential}` },
      });
      if (!response.ok) throw new Error("delete failed");
      onDeleted(lead.id);
    } catch {
      setError("The lead was not deleted. Owner access is required.");
      setBusy("");
    }
  };
  const runDraft = async () => {
    if (!lead || !prompt.trim()) return;
    setBusy("draft");
    setDraft("");
    setError("");
    try {
      const result = await operationsApi<{ summary: string }>("/api/benson/v1/ai/runs", credential, {
        method: "POST",
        body: JSON.stringify({ skill_id: skillId, prompt, lead_id: lead.id }),
      });
      setDraft(result.summary);
    } catch {
      setError("The Benson Assistant is unavailable. No lead data was changed.");
    } finally {
      setBusy("");
    }
  };
  return {
    assignee,
    busy,
    draft,
    edit,
    error,
    lead,
    note,
    prompt,
    skillId,
    skills,
    staff,
    setAssignee,
    setEdit,
    setError,
    setNote,
    setPrompt,
    setSkillId,
    deleteLead,
    runDraft,
    save,
  };
}
