import { ArrowLeft, FileLock2, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { onboardingApi } from "./onboardingApi";
import { EmployeeIdentitySection } from "./EmployeeIdentitySection";
import { OnboardingReviewActions } from "./OnboardingReviewActions";
import type { ApplicabilityReviewInput, OnboardingDocument, OnboardingTask, TaskReviewInput } from "./onboardingTypes";
import type { OnboardingEmployee } from "./onboardingTypes";

export function EmployeeReviewPanel({
  credential,
  employee,
  onEmployeeChanged,
  onBack,
}: {
  credential: string;
  employee: OnboardingEmployee;
  onEmployeeChanged(): Promise<unknown>;
  onBack(): void;
}) {
  const [tasks, setTasks] = useState<OnboardingTask[]>([]);
  const [documents, setDocuments] = useState<OnboardingDocument[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [nextTasks, nextDocuments] = await Promise.all([
        onboardingApi.listEmployeeTasks(credential, employee.id),
        onboardingApi.listEmployeeDocuments(credential, employee.id),
      ]);
      setTasks(nextTasks);
      setDocuments(nextDocuments);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Review data unavailable");
    }
  }, [credential, employee.id]);

  useEffect(() => void load(), [load]);

  const update = async (task: OnboardingTask, action: () => Promise<OnboardingTask>) => {
    setBusy(task.id);
    setError("");
    try {
      const changed = await action();
      setTasks((current) => current.map((item) => (item.id === changed.id ? changed : item)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Onboarding review failed");
    } finally {
      setBusy("");
    }
  };

  const upload = async (task: OnboardingTask, file?: File) => {
    if (!file) return;
    setBusy(task.id);
    setError("");
    try {
      await onboardingApi.submitEmployerEvidence(credential, employee.id, task, file);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Employer evidence could not be uploaded");
    } finally {
      setBusy("");
    }
  };

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
      {error && <p className="form-error">{error}</p>}
      <EmployeeIdentitySection
        credential={credential}
        employee={employee}
        onEmployeeChanged={onEmployeeChanged}
      />
      <div className="review-task-list">
        {tasks.map((task) => (
          <article className="review-task" key={task.id}>
            <div className="review-task-copy">
              <span className={`task-status status-${task.status}`}>{task.status.replace("_", " ")}</span>
              <h2>{task.label}</h2>
              <p>{task.instructions}</p>
              {task.official_source.startsWith("https://") && (
                <a className="official-form-link" href={task.official_source} rel="noreferrer" target="_blank">
                  Open official form or instructions
                </a>
              )}
              <small>{task.applicability_reason}</small>
            </div>
            <div className="protected-files">
              {documents
                .filter((item) => item.task_id === task.id)
                .map((document) => (
                  <button
                    key={document.id}
                    onClick={() => void onboardingApi.downloadEmployeeDocument(credential, employee.id, document)}
                  >
                    <FileLock2 /> {document.original_name} · v{document.version}
                  </button>
                ))}
            </div>
            {task.responsible_party === "employer" && task.status === "pending" && (
              <label className="upload-control">
                <Upload /> Upload employer evidence
                <input
                  accept="application/pdf,image/jpeg,image/png,image/webp"
                  disabled={busy === task.id}
                  type="file"
                  onChange={(event) => void upload(task, event.target.files?.[0])}
                />
              </label>
            )}
            <OnboardingReviewActions
              busy={busy === task.id}
              onApplicability={(review: ApplicabilityReviewInput) =>
                update(task, () => onboardingApi.reviewApplicability(credential, employee.id, task.id, review))
              }
              onTaskReview={(review: TaskReviewInput) =>
                update(task, () => onboardingApi.reviewTask(credential, employee.id, task.id, review))
              }
              task={task}
            />
          </article>
        ))}
      </div>
    </section>
  );
}
