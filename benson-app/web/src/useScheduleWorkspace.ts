import { useEffect, useState } from "react";
import { requestHeaders } from "./api";
import type { ScheduleDraft } from "./ScheduleForm";
import type { Job, ScheduleEntry, StaffMember } from "./types";

async function apiError(response: Response, fallback: string) {
  const payload = (await response.json().catch(() => ({}))) as { detail?: string };
  return payload.detail || fallback;
}

export function useScheduleWorkspace(credential: string, canPlan: boolean) {
  const [entries, setEntries] = useState<ScheduleEntry[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [status, setStatus] = useState("Loading schedule…");
  const headers = { ...requestHeaders(credential), "content-type": "application/json" };
  useEffect(() => {
    const controller = new AbortController();
    const schedule = fetch("/api/benson/v1/schedule", {
      headers: requestHeaders(credential),
      signal: controller.signal,
    });
    const plannerData = canPlan
      ? Promise.all([
          fetch("/api/benson/v1/jobs", { headers: requestHeaders(credential), signal: controller.signal }),
          fetch("/api/benson/v1/staff", { headers: requestHeaders(credential), signal: controller.signal }),
        ])
      : Promise.resolve(null);
    Promise.all([schedule, plannerData])
      .then(async ([scheduleResponse, plannerResponses]) => {
        if (!scheduleResponse.ok || plannerResponses?.some((response) => !response.ok)) {
          throw new Error("Schedule API unavailable");
        }
        setEntries((await scheduleResponse.json()) as ScheduleEntry[]);
        if (plannerResponses) {
          const available = (await plannerResponses[0].json()) as Job[];
          const directory = (await plannerResponses[1].json()) as { staff: StaffMember[] };
          setJobs(available.filter((job) => ["planned", "active"].includes(job.status)));
          setStaff(directory.staff);
        }
        setStatus("");
      })
      .catch((error) => {
        if (error instanceof Error && error.name !== "AbortError") setStatus("Unable to load the schedule.");
      });
    return () => controller.abort();
  }, [canPlan, credential]);
  const save = async (draft: ScheduleDraft, entry?: ScheduleEntry) => {
    setStatus("Saving schedule…");
    const payload = entry
      ? {
          expected_version: entry.version,
          event_type: draft.event_type,
          starts_at: draft.starts_at,
          ends_at: draft.ends_at,
          timezone: draft.timezone,
          assigned_to: draft.assigned_to,
        }
      : draft;
    const response = await fetch(entry ? `/api/benson/v1/schedule/${entry.id}` : "/api/benson/v1/schedule", {
      method: entry ? "PATCH" : "POST",
      headers,
      body: JSON.stringify(payload),
    });
    if (!response.ok) return (setStatus(await apiError(response, "Unable to save the schedule.")), false);
    const changed = (await response.json()) as ScheduleEntry;
    setEntries((current) =>
      entry ? current.map((item) => (item.id === changed.id ? changed : item)) : [...current, changed],
    );
    setStatus(entry ? "Schedule updated." : "Work added to the schedule.");
    return true;
  };
  const transition = async (entry: ScheduleEntry, target: ScheduleEntry["status"]) => {
    const needsNote = ["completed", "cancelled"].includes(target);
    const note = needsNote ? window.prompt("Record a factual note for this schedule change:") : "";
    if (needsNote && !note?.trim()) return;
    setStatus("Updating schedule…");
    const response = await fetch(`/api/benson/v1/schedule/${entry.id}/transition`, {
      method: "POST",
      headers,
      body: JSON.stringify({ expected_version: entry.version, status: target, note: note || "" }),
    });
    if (!response.ok) return setStatus(await apiError(response, "Unable to update the schedule."));
    const changed = (await response.json()) as ScheduleEntry;
    setEntries((current) => current.map((item) => (item.id === changed.id ? changed : item)));
    setStatus(`Schedule marked ${changed.status.replace("_", " ")}.`);
  };
  return { entries, jobs, save, staff, status, transition };
}
