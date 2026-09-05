import { useState } from "react";
import type { Job, ScheduleEntry, StaffMember } from "./types";

export type ScheduleDraft = {
  job_id: string;
  event_type: ScheduleEntry["event_type"];
  starts_at: string;
  ends_at: string;
  timezone: ScheduleEntry["timezone"];
  assigned_to: string;
};

function localInput(iso?: string) {
  if (!iso) return "";
  const date = new Date(iso);
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
    .format(date)
    .replace(" ", "T");
}

type RepeatedHour = "auto" | "-07:00" | "-08:00";

function pacificRfc3339(value: string, repeatedHour: RepeatedHour) {
  const validOffsets = (["-07:00", "-08:00"] as const).filter((offset) => {
    const candidate = new Date(`${value}:00${offset}`);
    return localInput(candidate.toISOString()) === value;
  });
  if (!validOffsets.length) throw new Error("This local time does not exist because the clock moves forward.");
  if (validOffsets.length > 1 && repeatedHour === "auto") {
    throw new Error("This local time occurs twice. Choose the first or second occurrence.");
  }
  const offset = validOffsets.length === 1 ? validOffsets[0] : validOffsets.find((item) => item === repeatedHour);
  if (!offset) throw new Error("The repeated-hour choice does not match this time.");
  return `${value}:00${offset}`;
}

export function ScheduleForm({
  entry,
  jobs,
  staff,
  onCancel,
  onSave,
}: {
  entry?: ScheduleEntry;
  jobs: Job[];
  staff: StaffMember[];
  onCancel(): void;
  onSave(draft: ScheduleDraft): void;
}) {
  const [jobId, setJobId] = useState(entry?.job_id || jobs[0]?.id || "");
  const [eventType, setEventType] = useState<ScheduleEntry["event_type"]>(entry?.event_type || "work");
  const [startsAt, setStartsAt] = useState(localInput(entry?.starts_at));
  const [endsAt, setEndsAt] = useState(localInput(entry?.ends_at));
  const [assignedTo, setAssignedTo] = useState(entry?.assigned_to || "");
  const [startRepeatedHour, setStartRepeatedHour] = useState<RepeatedHour>("auto");
  const [endRepeatedHour, setEndRepeatedHour] = useState<RepeatedHour>("auto");
  const [validation, setValidation] = useState("");
  return (
    <form
      className="schedule-form"
      onSubmit={(event) => {
        event.preventDefault();
        try {
          const startsUtc = pacificRfc3339(startsAt, startRepeatedHour);
          const endsUtc = pacificRfc3339(endsAt, endRepeatedHour);
          if (Date.parse(endsUtc) <= Date.parse(startsUtc)) throw new Error("End time must be after the start time.");
          setValidation("");
          onSave({
            job_id: jobId,
            event_type: eventType,
            starts_at: startsUtc,
            ends_at: endsUtc,
            timezone: "America/Los_Angeles",
            assigned_to: assignedTo,
          });
        } catch (error) {
          setValidation(error instanceof Error ? error.message : "Enter a valid schedule time.");
        }
      }}
    >
      <div>
        <p>FIELD COORDINATION</p>
        <h1>{entry ? "Edit scheduled work" : "Schedule work"}</h1>
      </div>
      <label>
        Job
        <select disabled={Boolean(entry)} required value={jobId} onChange={(event) => setJobId(event.target.value)}>
          <option value="">Select a job</option>
          {jobs.map((job) => (
            <option key={job.id} value={job.id}>
              {job.number} · {job.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        Visit type
        <select value={eventType} onChange={(event) => setEventType(event.target.value as ScheduleEntry["event_type"])}>
          <option value="site_visit">Site visit</option>
          <option value="work">Work</option>
          <option value="inspection">Inspection</option>
          <option value="delivery">Delivery</option>
        </select>
      </label>
      <label>
        Time zone
        <select aria-describedby="timezone-help" value="America/Los_Angeles" disabled>
          <option value="America/Los_Angeles">Pacific time — America/Los_Angeles</option>
        </select>
        <small id="timezone-help">Times are saved as UTC and shown in Pacific time.</small>
      </label>
      <div className="schedule-form-grid">
        <label>
          Starts
          <input
            required
            type="datetime-local"
            value={startsAt}
            onChange={(event) => setStartsAt(event.target.value)}
          />
        </label>
        <label>
          Ends
          <input required type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} />
        </label>
      </div>
      <label>
        Start repeated-hour choice
        <select
          value={startRepeatedHour}
          onChange={(event) => setStartRepeatedHour(event.target.value as RepeatedHour)}
        >
          <option value="auto">Automatic — reject ambiguous times</option>
          <option value="-07:00">First occurrence — daylight time</option>
          <option value="-08:00">Second occurrence — standard time</option>
        </select>
      </label>
      <label>
        End repeated-hour choice
        <select value={endRepeatedHour} onChange={(event) => setEndRepeatedHour(event.target.value as RepeatedHour)}>
          <option value="auto">Automatic — reject ambiguous times</option>
          <option value="-07:00">First occurrence — daylight time</option>
          <option value="-08:00">Second occurrence — standard time</option>
        </select>
      </label>
      <label>
        Assigned to
        <select required value={assignedTo} onChange={(event) => setAssignedTo(event.target.value)}>
          <option value="">Select staff</option>
          {staff.map((member) => (
            <option key={member.email} value={member.email}>
              {member.display_name} · {member.email}
            </option>
          ))}
        </select>
      </label>
      {validation && (
        <p className="form-error" role="alert">
          {validation}
        </p>
      )}
      <div className="form-actions">
        <button className="primary" type="submit">
          {entry ? "Save schedule" : "Add to schedule"}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
