import { ArrowLeft, FileLock2 } from "lucide-react";
import { useEffect, useState } from "react";
import { operationsApi, requestHeaders } from "./api";
import type { Employee, EmployeeDocument, EmployeeTask } from "./types";

export function EmployeeReviewPanel({
  credential,
  employee,
  onBack,
}: {
  credential: string;
  employee: Employee;
  onBack(): void;
}) {
  const [tasks, setTasks] = useState<EmployeeTask[]>([]);
  const [documents, setDocuments] = useState<EmployeeDocument[]>([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([
      operationsApi<EmployeeTask[]>(`/api/benson/v1/employees/${employee.id}/tasks`, credential),
      operationsApi<EmployeeDocument[]>(`/api/benson/v1/employees/${employee.id}/documents`, credential),
    ])
      .then(([nextTasks, nextDocuments]) => {
        if (active) {
          setTasks(nextTasks);
          setDocuments(nextDocuments);
        }
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Review data unavailable"));
    return () => {
      active = false;
    };
  }, [credential, employee.id]);
  const review = async (task: EmployeeTask, decision: "complete" | "reject" | "not_applicable") => {
    if (!comment.trim()) {
      setError("Add a review note before changing a task.");
      return;
    }
    setBusy(task.id);
    setError("");
    try {
      const updated = await operationsApi<EmployeeTask>(
        `/api/benson/v1/employees/${employee.id}/tasks/${task.id}`,
        credential,
        { method: "PATCH", body: JSON.stringify({ decision, comment }) },
      );
      setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setComment("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Task review failed");
    } finally {
      setBusy("");
    }
  };
  const openDocument = async (document: EmployeeDocument) => {
    setError("");
    const response = await fetch(`/api/benson/v1/employees/${employee.id}/documents/${document.id}`, {
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
  const documentsFor = (taskId: string) => documents.filter((document) => document.task_id === taskId);
  return (
    <section className="employee-review">
      <button className="back-button" onClick={onBack}>
        <ArrowLeft /> Employee roster
      </button>
      <div className="review-head">
        <div>
          <div className="section-kicker">ONBOARDING REVIEW</div>
          <h1>{employee.name}</h1>
          <p>
            {employee.email} · {employee.work_location}
          </p>
        </div>
        <span className="license-pill">No paid Workspace license</span>
      </div>
      <label className="review-comment">
        Review note
        <textarea
          placeholder="Required for completion, rejection, or not-applicable decisions"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="review-task-list">
        {tasks.map((task) => (
          <article className="review-task" key={task.id}>
            <div className="review-task-copy">
              <span className={`task-status status-${task.status}`}>{task.status.replace("_", " ")}</span>
              <h2>{task.label}</h2>
              <p>{task.instructions}</p>
              <small>{task.applicability_reason}</small>
            </div>
            <div className="protected-files">
              {documentsFor(task.id).map((document) => (
                <button key={document.id} onClick={() => void openDocument(document)}>
                  <FileLock2 /> {document.original_name} · v{document.version}
                </button>
              ))}
            </div>
            <div className="review-actions">
              {task.status === "submitted" && (
                <>
                  <button disabled={busy === task.id} onClick={() => void review(task, "complete")}>
                    Approve
                  </button>
                  <button disabled={busy === task.id} onClick={() => void review(task, "reject")}>
                    Reject
                  </button>
                </>
              )}
              {!["completed", "not_applicable"].includes(task.status) && (
                <button
                  className="text-button"
                  disabled={busy === task.id}
                  onClick={() => void review(task, "not_applicable")}
                >
                  Mark not applicable
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
