import { useCallback, useEffect, useState } from "react";
import { requestHeaders } from "./api";
import { emptyFieldReportDraft, FieldReportForm, type FieldReportDraft } from "./FieldReportForm";
import type { FieldReport, Job } from "./types";

async function detail(response: Response, fallback: string) {
  const body = (await response.json().catch(() => ({}))) as { detail?: string };
  return body.detail || fallback;
}

function reportDraft(report: FieldReport): FieldReportDraft {
  return {
    job_id: report.job_id,
    service_date: report.service_date,
    workforce_total: report.workforce_total,
    workforce_hours: report.workforce_hours,
    weather: report.weather,
    completed_work: report.completed_work,
    materials: report.materials,
    equipment: report.equipment,
    delays: report.delays,
    issues: report.issues,
    safety_observations: report.safety_observations,
  };
}

export function FieldRecordWorkspace({ credential, role }: { credential: string; role: string }) {
  const [reports, setReports] = useState<FieldReport[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [editing, setEditing] = useState<FieldReport | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<FieldReportDraft>(emptyFieldReportDraft);
  const [status, setStatus] = useState("Loading field records…");
  const headers = requestHeaders(credential);
  const load = useCallback(async () => {
    const [reportResponse, jobResponse] = await Promise.all([
      fetch("/api/benson/v1/field-records", { headers }),
      fetch("/api/benson/v1/jobs", { headers }),
    ]);
    if (!reportResponse.ok || !jobResponse.ok) throw new Error("Field records unavailable");
    setReports((await reportResponse.json()) as FieldReport[]);
    setJobs(((await jobResponse.json()) as Job[]).filter((job) => ["planned", "active"].includes(job.status)));
    setStatus("");
  }, [credential]);
  useEffect(() => {
    void load().catch(() => setStatus("Unable to load field records."));
  }, [load]);
  const begin = (report?: FieldReport) => {
    setEditing(report || null);
    setCreating(true);
    setDraft(report ? reportDraft(report) : { ...emptyFieldReportDraft, job_id: jobs[0]?.id || "" });
  };
  const save = async () => {
    setStatus("Saving field report…");
    const payload = editing
      ? { ...draft, job_id: undefined, service_date: undefined, expected_version: editing.version }
      : draft;
    const response = await fetch(
      editing ? `/api/benson/v1/field-records/${editing.id}` : "/api/benson/v1/field-records",
      {
        method: editing ? "PUT" : "POST",
        headers: { ...headers, "content-type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) return setStatus(await detail(response, "Unable to save field report."));
    const saved = (await response.json()) as FieldReport;
    setReports((current) =>
      editing ? current.map((item) => (item.id === saved.id ? saved : item)) : [saved, ...current],
    );
    setEditing(null);
    setCreating(false);
    setStatus("Draft saved.");
  };
  const submit = async (report: FieldReport) => {
    const response = await fetch(
      `/api/benson/v1/field-records/${report.id}/submit?expected_version=${report.version}`,
      { method: "POST", headers },
    );
    if (!response.ok) return setStatus(await detail(response, "Unable to submit field report."));
    const saved = (await response.json()) as FieldReport;
    setReports((current) => current.map((item) => (item.id === saved.id ? saved : item)));
    setStatus("Field report submitted and locked.");
  };
  const upload = async (report: FieldReport, file: File) => {
    const body = new FormData();
    body.set("stage", "during");
    body.set("photo", file);
    const response = await fetch(`/api/benson/v1/field-records/${report.id}/photos`, {
      method: "POST",
      headers,
      body,
    });
    setStatus(response.ok ? "Private photo added." : await detail(response, "Unable to add photo."));
  };
  if (creating) {
    return (
      <FieldReportForm
        canCancel={reports.length > 0}
        draft={draft}
        editing={Boolean(editing)}
        jobs={jobs}
        onCancel={() => {
          setEditing(null);
          setCreating(false);
        }}
        onSave={() => void save()}
        setDraft={setDraft}
        status={status}
      />
    );
  }
  return (
    <section className="schedule-workspace" aria-labelledby="field-heading">
      <div className="headline">
        <div>
          <p>FIELD DELIVERY</p>
          <h1 id="field-heading">Field records</h1>
          <span>Versioned daily job records and private progress photos.</span>
        </div>
        <button className="primary" disabled={!jobs.length} onClick={() => begin()}>
          + Daily report
        </button>
      </div>
      {status && (
        <p role="status" className="form-status">
          {status}
        </p>
      )}
      {!reports.length && !status && (
        <div className="empty">
          <h2>No field reports</h2>
          <p>No daily records have been filed yet.</p>
        </div>
      )}
      <div className="schedule-list">
        {reports.map((report) => (
          <article key={report.id}>
            <div>
              <small>
                {report.job_number} · {report.service_date} · revision {report.revision}
              </small>
              <h3>{report.job_title}</h3>
              <p>{report.completed_work || "Draft in progress"}</p>
            </div>
            <span className={`schedule-status ${report.status}`}>{report.status.replace("_", " ")}</span>
            <div className="row-actions">
              {report.status === "draft" && (
                <>
                  <button onClick={() => begin(report)}>Edit</button>
                  <label className="button">
                    Add photo
                    <input
                      className="visually-hidden"
                      aria-label={`Add photo to ${report.job_number}`}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) void upload(report, file);
                      }}
                    />
                  </label>
                  <button className="primary" onClick={() => void submit(report)}>
                    Submit
                  </button>
                </>
              )}
              {report.status === "correction_required" && role === "field" && <span>Correction requested</span>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
