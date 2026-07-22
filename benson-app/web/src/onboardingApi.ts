import { operationsApi, requestHeaders } from "./api";
import type {
  ApplicabilityReviewInput,
  IdentityProvisioningCommand,
  NewEmployeeInput,
  OnboardingDocument,
  OnboardingEmployee,
  OnboardingSignature,
  OnboardingTask,
  OnboardingTaskPayload,
  TaskReviewInput,
} from "./onboardingTypes";

async function downloadDocument(url: string, credential: string, fileName: string): Promise<void> {
  const response = await fetch(url, { headers: requestHeaders(credential) });
  if (!response.ok) throw new Error("Protected document could not be opened.");
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = window.document.createElement("a");
  link.href = objectUrl;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

export const onboardingApi = {
  listEmployees(credential: string): Promise<OnboardingEmployee[]> {
    return operationsApi("/api/benson/v1/employees", credential);
  },

  createEmployee(credential: string, employee: NewEmployeeInput): Promise<OnboardingEmployee> {
    return operationsApi("/api/benson/v1/employees", credential, {
      method: "POST",
      body: JSON.stringify(employee),
    });
  },

  inviteEmployee(credential: string, employee: OnboardingEmployee): Promise<{ version: number }> {
    return operationsApi(`/api/benson/v1/employees/${employee.id}/invite`, credential, {
      method: "POST",
      body: JSON.stringify({ expected_version: employee.version }),
    });
  },

  listEmployeeTasks(credential: string, employeeId: string): Promise<OnboardingTask[]> {
    return operationsApi(`/api/benson/v1/employees/${employeeId}/tasks`, credential);
  },

  listEmployeeDocuments(credential: string, employeeId: string): Promise<OnboardingDocument[]> {
    return operationsApi(`/api/benson/v1/employees/${employeeId}/documents`, credential);
  },

  listEmployeeSignatures(credential: string, employeeId: string): Promise<OnboardingSignature[]> {
    return operationsApi(`/api/benson/v1/employees/${employeeId}/signatures`, credential);
  },

  listIdentityCommands(credential: string, employeeId: string): Promise<IdentityProvisioningCommand[]> {
    return operationsApi(`/api/benson/v1/employees/${employeeId}/identity-provisioning`, credential);
  },

  requestIdentity(
    credential: string,
    employee: OnboardingEmployee,
    idempotencyKey: string,
  ): Promise<IdentityProvisioningCommand> {
    return operationsApi("/api/benson/v1/identity-provisioning", credential, {
      method: "POST",
      body: JSON.stringify({
        employee_id: employee.id,
        expected_version: employee.version,
        idempotency_key: idempotencyKey,
      }),
    });
  },

  approveIdentity(credential: string, command: IdentityProvisioningCommand): Promise<IdentityProvisioningCommand> {
    return operationsApi(`/api/benson/v1/identity-provisioning/${command.id}/approve`, credential, {
      method: "POST",
      body: JSON.stringify({ expected_version: command.version }),
    });
  },

  confirmIdentity(
    credential: string,
    command: IdentityProvisioningCommand,
    reason: string,
    evidenceReference: string,
  ): Promise<IdentityProvisioningCommand> {
    return operationsApi(`/api/benson/v1/identity-provisioning/${command.id}/admin-confirm`, credential, {
      method: "POST",
      body: JSON.stringify({
        expected_version: command.version,
        confirmed_no_paid_license: true,
        reason,
        evidence_reference: evidenceReference,
      }),
    });
  },

  confirmManualIdentity(
    credential: string,
    command: IdentityProvisioningCommand,
    temporaryPassword: string,
    reason: string,
    evidenceReference: string,
  ): Promise<IdentityProvisioningCommand> {
    return operationsApi(
      `/api/benson/v1/identity-provisioning/${command.id}/manual-confirm-and-invite`,
      credential,
      {
        method: "POST",
        body: JSON.stringify({
          expected_version: command.version,
          confirmed_account_created: true,
          confirmed_no_paid_license: true,
          temporary_password: temporaryPassword,
          reason,
          evidence_reference: evidenceReference,
        }),
      },
    );
  },

  reissueIdentityInvite(
    credential: string,
    command: IdentityProvisioningCommand,
    temporaryPassword: string,
    reason: string,
    evidenceReference: string,
  ): Promise<IdentityProvisioningCommand> {
    return operationsApi(`/api/benson/v1/identity-provisioning/${command.id}/reissue-invite`, credential, {
      method: "POST",
      body: JSON.stringify({
        expected_version: command.version,
        confirmed_password_reset: true,
        confirmed_no_paid_license: true,
        temporary_password: temporaryPassword,
        reason,
        evidence_reference: evidenceReference,
      }),
    });
  },

  reviewTask(credential: string, employeeId: string, taskId: string, review: TaskReviewInput): Promise<OnboardingTask> {
    return operationsApi(`/api/benson/v1/employees/${employeeId}/tasks/${taskId}`, credential, {
      method: "PATCH",
      body: JSON.stringify(review),
    });
  },

  reviewApplicability(
    credential: string,
    employeeId: string,
    taskId: string,
    review: ApplicabilityReviewInput,
  ): Promise<OnboardingTask> {
    return operationsApi(`/api/benson/v1/employees/${employeeId}/tasks/${taskId}/applicability`, credential, {
      method: "PATCH",
      body: JSON.stringify(review),
    });
  },

  employeeTasks(credential: string): Promise<OnboardingTaskPayload> {
    return operationsApi("/api/benson/v1/onboarding/tasks", credential);
  },

  employeeDocuments(credential: string): Promise<OnboardingDocument[]> {
    return operationsApi("/api/benson/v1/onboarding/documents", credential);
  },

  employeeSignatures(credential: string): Promise<OnboardingSignature[]> {
    return operationsApi("/api/benson/v1/onboarding/signatures", credential);
  },

  submitEvidence(credential: string, task: OnboardingTask, file: File): Promise<OnboardingDocument> {
    const body = new FormData();
    body.append("expected_version", String(task.version));
    body.append("file", file);
    return operationsApi(`/api/benson/v1/onboarding/tasks/${task.id}/evidence`, credential, {
      method: "POST",
      body,
    });
  },

  submitEmployerEvidence(
    credential: string,
    employeeId: string,
    task: OnboardingTask,
    file: File,
  ): Promise<OnboardingDocument> {
    const body = new FormData();
    body.append("expected_version", String(task.version));
    body.append("file", file);
    return operationsApi(`/api/benson/v1/employees/${employeeId}/tasks/${task.id}/evidence`, credential, {
      method: "POST",
      body,
    });
  },

  submitSignature(credential: string, task: OnboardingTask, typedName: string): Promise<OnboardingSignature> {
    return operationsApi(`/api/benson/v1/onboarding/tasks/${task.id}/signature`, credential, {
      method: "POST",
      body: JSON.stringify({ expected_version: task.version, typed_name: typedName, accepted: true }),
    });
  },

  downloadOwnDocument(credential: string, document: OnboardingDocument): Promise<void> {
    return downloadDocument(`/api/benson/v1/onboarding/documents/${document.id}`, credential, document.original_name);
  },

  downloadEmployeeDocument(credential: string, employeeId: string, document: OnboardingDocument): Promise<void> {
    return downloadDocument(
      `/api/benson/v1/employees/${employeeId}/documents/${document.id}`,
      credential,
      document.original_name,
    );
  },
};
