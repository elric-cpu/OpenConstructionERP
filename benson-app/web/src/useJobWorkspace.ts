import { useEffect, useState } from "react";
import { requestHeaders } from "./api";
import type { JobPlan } from "./JobPlanForm";
import type { Estimate, Job, StaffMember } from "./types";

export function useJobWorkspace(credential: string, canPlan: boolean) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [estimates, setEstimates] = useState<Estimate[]>([]);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [status, setStatus] = useState("loading");
  const headers = { ...requestHeaders(credential), "content-type": "application/json" };
  useEffect(() => {
    const controller = new AbortController();
    const plannerData = canPlan
      ? Promise.all([
          fetch("/api/benson/v1/estimates?status=accepted", {
            headers: requestHeaders(credential),
            signal: controller.signal,
          }),
          fetch("/api/benson/v1/staff", { headers: requestHeaders(credential), signal: controller.signal }),
        ])
      : Promise.resolve(null);
    Promise.all([
      fetch("/api/benson/v1/jobs", { headers: requestHeaders(credential), signal: controller.signal }),
      plannerData,
    ])
      .then(async ([jobResponse, plannerResponses]) => {
        if (!jobResponse.ok || plannerResponses?.some((response) => !response.ok)) {
          throw new Error("Job API unavailable");
        }
        setJobs((await jobResponse.json()) as Job[]);
        if (plannerResponses) {
          const directory = (await plannerResponses[1].json()) as { staff: StaffMember[] };
          setEstimates((await plannerResponses[0].json()) as Estimate[]);
          setStaff(directory.staff);
        }
        setStatus("");
      })
      .catch((error) => {
        if (error instanceof Error && error.name !== "AbortError") setStatus("Unable to load jobs.");
      });
    return () => controller.abort();
  }, [canPlan, credential]);
  const create = async (estimate: Estimate, plan: JobPlan) => {
    setStatus("saving");
    const response = await fetch(`/api/benson/v1/jobs/from-estimate/${estimate.id}`, {
      method: "POST",
      headers,
      body: JSON.stringify(plan),
    });
    if (!response.ok) return (setStatus("Unable to create job."), false);
    const job = (await response.json()) as Job;
    setJobs((current) => [job, ...current]);
    setEstimates((current) => current.filter((item) => item.id !== estimate.id));
    setStatus("Planned job created from accepted estimate.");
    return true;
  };
  const update = async (job: Job, plan: JobPlan) => {
    setStatus("saving");
    const response = await fetch(`/api/benson/v1/jobs/${job.id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(plan),
    });
    if (!response.ok) return (setStatus("Unable to save job plan."), false);
    const changed = (await response.json()) as Job;
    setJobs((current) => current.map((item) => (item.id === changed.id ? changed : item)));
    setStatus("Job plan saved.");
    return true;
  };
  const transition = async (job: Job, target: Job["status"]) => {
    const needsNote = ["on_hold", "completed", "cancelled"].includes(target);
    const note = needsNote ? window.prompt("Record the factual reason for this job status:") : "";
    if (needsNote && !note?.trim()) return;
    const response = await fetch(`/api/benson/v1/jobs/${job.id}/transition`, {
      method: "POST",
      headers,
      body: JSON.stringify({ status: target, note: note || "" }),
    });
    if (!response.ok) return setStatus("Unable to change job status.");
    const changed = (await response.json()) as Job;
    setJobs((current) => current.map((item) => (item.id === changed.id ? changed : item)));
    setStatus(`Job marked ${changed.status.replace("_", " ")}.`);
  };
  return { create, estimates, jobs, staff, status, transition, update };
}
