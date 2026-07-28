import { useCallback, useEffect, useState } from "react";
import { onboardingApi } from "./onboardingApi";
import type {
  NewEmployeeInput,
  OnboardingDocument,
  OnboardingEmployee,
  OnboardingSignature,
  OnboardingTask,
} from "./onboardingTypes";
import { useIdentityProvisioning } from "./useIdentityProvisioning";

type WorkspaceStatus = "loading" | "ready" | "saving" | "error";

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export function useOnboardingWorkspace(credential: string) {
  const [employees, setEmployees] = useState<OnboardingEmployee[]>([]);
  const [selected, setSelected] = useState<OnboardingEmployee | null>(null);
  const [tasks, setTasks] = useState<OnboardingTask[]>([]);
  const [documents, setDocuments] = useState<OnboardingDocument[]>([]);
  const [signatures, setSignatures] = useState<OnboardingSignature[]>([]);
  const [status, setStatus] = useState<WorkspaceStatus>("loading");
  const [error, setError] = useState("");

  const reportError = useCallback((message: string) => {
    setError(message);
    setStatus("error");
  }, []);
  const setSaving = useCallback((saving: boolean) => {
    if (saving) setError("");
    setStatus(saving ? "saving" : "ready");
  }, []);

  const loadEmployees = useCallback(async () => {
    setError("");
    setStatus("loading");
    try {
      setEmployees(await onboardingApi.listEmployees(credential));
      setStatus("ready");
    } catch (reason) {
      setError(errorMessage(reason, "Employees unavailable"));
      setStatus("error");
    }
  }, [credential]);

  useEffect(() => {
    void loadEmployees();
  }, [loadEmployees]);

  const refreshSelectedEmployee = useCallback(async () => {
    const records = await onboardingApi.listEmployees(credential);
    setEmployees(records);
    if (selected) {
      const refreshed = records.find((employee) => employee.id === selected.id) ?? null;
      setSelected(refreshed);
      return refreshed;
    }
    return null;
  }, [credential, selected]);

  const identity = useIdentityProvisioning({
    credential,
    onEmployeeChanged: refreshSelectedEmployee,
    onError: reportError,
    selected,
    setSaving,
  });

  const selectEmployee = useCallback(
    async (employee: OnboardingEmployee) => {
      setSelected(employee);
      setError("");
      setStatus("loading");
      try {
        const [nextTasks, nextDocuments, nextSignatures] = await Promise.all([
          onboardingApi.listEmployeeTasks(credential, employee.id),
          onboardingApi.listEmployeeDocuments(credential, employee.id),
          onboardingApi.listEmployeeSignatures(credential, employee.id),
          identity.loadCommands(employee.id),
        ]);
        setTasks(nextTasks);
        setDocuments(nextDocuments);
        setSignatures(nextSignatures);
        setStatus("ready");
      } catch (reason) {
        setError(errorMessage(reason, "Review data unavailable"));
        setStatus("error");
      }
    },
    [credential, identity.loadCommands],
  );

  const createEmployee = useCallback(
    async (input: NewEmployeeInput) => {
      setStatus("saving");
      setError("");
      try {
        const employee = await onboardingApi.createEmployee(credential, input);
        setEmployees((current) => [...current, employee].sort((a, b) => a.name.localeCompare(b.name)));
        setStatus("ready");
        return employee;
      } catch (reason) {
        setError(errorMessage(reason, "New hire could not be saved"));
        setStatus("error");
        return null;
      }
    },
    [credential],
  );

  const inviteEmployee = useCallback(
    async (employee: OnboardingEmployee) => {
      setStatus("saving");
      setError("");
      try {
        const receipt = await onboardingApi.inviteEmployee(credential, employee);
        const invited = { ...employee, status: "invited" as const, version: receipt.version };
        setEmployees((current) => current.map((item) => (item.id === invited.id ? invited : item)));
        if (selected?.id === invited.id) setSelected(invited);
        setStatus("ready");
      } catch (reason) {
        setError(errorMessage(reason, "Invitation could not be queued"));
        setStatus("error");
      }
    },
    [credential, selected?.id],
  );

  const updateTask = useCallback((task: OnboardingTask) => {
    setTasks((current) => current.map((item) => (item.id === task.id ? task : item)));
  }, []);

  const closeEmployee = useCallback(() => {
    setSelected(null);
    setTasks([]);
    setDocuments([]);
    setSignatures([]);
    identity.clearCommands();
    setError("");
    setStatus("ready");
  }, [identity.clearCommands]);

  return {
    approveIdentity: identity.approveIdentity,
    closeEmployee,
    confirmIdentity: identity.confirmIdentity,
    createEmployee,
    documents,
    employees,
    error,
    identityCommands: identity.commands,
    inviteEmployee,
    loadEmployees,
    requestIdentity: identity.requestIdentity,
    selected,
    selectEmployee,
    setDocuments,
    setError,
    setSignatures,
    setTasks,
    signatures,
    status,
    tasks,
    updateTask,
  };
}
