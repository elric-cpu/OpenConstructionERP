import { Check, FileLock2, ShieldAlert, Upload } from "lucide-react";
import { type CSSProperties, useState } from "react";
import { operationsApi, requestHeaders } from "./api";
import type { EmployeeDocument, EmployeeTask, PortalSession } from "./types";

export function EmployeeTasks({
  credential,
  documents,
  session,
  setDocuments,
  setTasks,
  tasks,
}: {
  credential: string;
  documents: EmployeeDocument[];
  session: PortalSession;
  setDocuments(value: EmployeeDocument[] | ((current: EmployeeDocument[]) => EmployeeDocument[])): void;
  setTasks(value: EmployeeTask[] | ((current: EmployeeTask[]) => EmployeeTask[])): void;
  tasks: EmployeeTask[];
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const completed = tasks.filter((task) => ["completed", "not_applicable"].includes(task.status)).length;
  const progress = tasks.length ? Math.round((completed / tasks.length) * 100) : 0;
  const upload = async (task: EmployeeTask, file?: File) => {
    if (!file) return;
    setBusy(task.id);
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const document = await operationsApi<EmployeeDocument>(
        `/api/benson/v1/onboarding/tasks/${task.id}/evidence`,
        credential,
        { method: "POST", body },
      );
      setDocuments((current) => [
        document,
        ...current.map((item) =>
          item.task_id === task.id && item.status === "active" ? { ...item, status: "superseded" as const } : item,
        ),
      ]);
      setTasks((current) => current.map((item) => (item.id === task.id ? { ...item, status: "submitted" } : item)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Evidence could not be uploaded");
    } finally {
      setBusy("");
    }
  };
  const openDocument = async (document: EmployeeDocument) => {
    const response = await fetch(`/api/benson/v1/onboarding/documents/${document.id}`, {
      headers: requestHeaders(credential),
    });
    if (!response.ok) {
      setError("Protected document could not be opened.");
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const link = window.document.createElement("a");
    link.href = url;
    link.download = document.original_name;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section className="tasks-workspace">
      <div className="task-hero">
        <div>
          <div className="section-kicker">EMPLOYEE TASKS</div>
          <h1>Welcome, {session.employee?.name.split(" ")[0] || "team member"}.</h1>
          <p>Complete each applicable item. Your progress and protected documents save automatically.</p>
        </div>
        <div className="progress-dial" style={{ "--progress": `${progress * 3.6}deg` } as CSSProperties}>
          <strong>{progress}%</strong>
          <small>
            {completed} of {tasks.length}
          </small>
        </div>
      </div>
      <div className="security-note">
        <ShieldAlert /> Identity, tax, and payment records are encrypted and access-audited.
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="employee-task-list">
        {tasks.map((task, index) => {
          const taskDocuments = documents.filter((document) => document.task_id === task.id);
          const canUpload =
            ["employee", "contractor"].includes(task.responsible_party) &&
            ["pending", "rejected"].includes(task.status);
          return (
            <article className="employee-task-card" key={task.id}>
              <div className="task-number">{String(index + 1).padStart(2, "0")}</div>
              <div className="task-copy">
                <div className="task-line">
                  <h2>{task.label}</h2>
                  <span className={`task-status status-${task.status}`}>{task.status.replace("_", " ")}</span>
                </div>
                <p>{task.instructions}</p>
                <small>
                  Due {task.due_date} · {task.applicability_reason}
                </small>
                <div className="task-documents">
                  {taskDocuments.map((document) => (
                    <button key={document.id} onClick={() => void openDocument(document)}>
                      <FileLock2 /> {document.original_name} <small>v{document.version}</small>
                    </button>
                  ))}
                </div>
              </div>
              <div className="task-action">
                {canUpload && (
                  <label className="upload-control">
                    <Upload />{" "}
                    {busy === task.id
                      ? "Encrypting…"
                      : task.status === "rejected"
                        ? "Upload revision"
                        : "Upload evidence"}
                    <input
                      accept="application/pdf,image/jpeg,image/png,image/webp"
                      disabled={busy === task.id}
                      type="file"
                      onChange={(event) => void upload(task, event.target.files?.[0])}
                    />
                  </label>
                )}
                {task.status === "completed" && <Check className="task-check" aria-label="Completed" />}
                {task.status === "submitted" && <small>Waiting for Benson review</small>}
                {task.status === "blocked" && <small>Waiting for applicability review</small>}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
