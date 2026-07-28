import { useCallback, useEffect, useState } from "react";
import { onboardingApi } from "./onboardingApi";
import type { OnboardingDocument, OnboardingSignature, OnboardingTask } from "./onboardingTypes";

export function useEmployeeOnboarding(credential: string) {
  const [employeeName, setEmployeeName] = useState("");
  const [tasks, setTasks] = useState<OnboardingTask[]>([]);
  const [documents, setDocuments] = useState<OnboardingDocument[]>([]);
  const [signatures, setSignatures] = useState<OnboardingSignature[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [taskPayload, nextDocuments, nextSignatures] = await Promise.all([
        onboardingApi.employeeTasks(credential),
        onboardingApi.employeeDocuments(credential),
        onboardingApi.employeeSignatures(credential),
      ]);
      setEmployeeName(taskPayload.employee.name);
      setTasks(taskPayload.tasks);
      setDocuments(nextDocuments);
      setSignatures(nextSignatures);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Onboarding tasks are unavailable");
    } finally {
      setLoading(false);
    }
  }, [credential]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const uploadEvidence = useCallback(
    async (task: OnboardingTask, file: File) => {
      setBusy(task.id);
      setError("");
      try {
        await onboardingApi.submitEvidence(credential, task, file);
        await refresh();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Evidence could not be uploaded");
      } finally {
        setBusy("");
      }
    },
    [credential, refresh],
  );

  const submitSignature = useCallback(
    async (task: OnboardingTask, typedName: string) => {
      setBusy(task.id);
      setError("");
      try {
        await onboardingApi.submitSignature(credential, task, typedName);
        await refresh();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Acknowledgement could not be signed");
      } finally {
        setBusy("");
      }
    },
    [credential, refresh],
  );

  const openDocument = useCallback(
    async (document: OnboardingDocument) => {
      setError("");
      try {
        await onboardingApi.downloadOwnDocument(credential, document);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Protected document could not be opened");
      }
    },
    [credential],
  );

  return {
    busy,
    documents,
    employeeName,
    error,
    loading,
    openDocument,
    refresh,
    signatures,
    submitSignature,
    tasks,
    uploadEvidence,
  };
}
