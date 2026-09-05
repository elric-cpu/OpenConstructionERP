import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type {
  Employee,
  EmployeeActivation,
  EmployeeActivationPreview,
  EmployeeInput,
  Provisioning,
} from "./types";

const employeesKey = ["employees"];

export function useEmployees() {
  return useQuery({
    queryKey: employeesKey,
    queryFn: () => api.get<Employee[]>("/employees"),
  });
}

export function useSelectedEmployeeStatus(employee: Employee | null) {
  const awaitingActivation = Boolean(
    employee &&
    ["IDENTITY_REQUESTED", "IDENTITY_CREATED"].includes(employee.status) &&
    !employee.erp_access_confirmed_at,
  );
  return useQuery({
    queryKey: ["employee-status", employee?.id],
    queryFn: () => api.get<Employee>(`/employees/${employee!.id}`),
    enabled: awaitingActivation,
    refetchInterval: (query) =>
      query.state.data?.activation_sent_at || query.state.data?.erp_access_confirmed_at
        ? false
        : 2_000,
  });
}

export function useCreateEmployee() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: EmployeeInput) => api.post<Employee>("/employees", input),
    onSuccess: () => client.invalidateQueries({ queryKey: employeesKey }),
  });
}

export function useApproveEmployee() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ employee, reason }: { employee: Employee; reason: string }) =>
      api.post<{ employee: Employee; provisioning: Provisioning }>(
        `/employees/${employee.id}/approve`,
        { reason },
        { "If-Match": String(employee.version) },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: employeesKey }),
  });
}

export function useProvisioning(employee: Employee | null) {
  const tracksProvisioning = Boolean(
    employee && ["IDENTITY_REQUESTED", "IDENTITY_CREATED"].includes(employee.status),
  );
  return useQuery({
    queryKey: ["employee-provisioning", employee?.id],
    queryFn: () => api.get<Provisioning>(`/employees/${employee!.id}/provisioning`),
    enabled: tracksProvisioning,
    refetchInterval: (query) => (query.state.data?.status === "CREATED" ? false : 2_000),
  });
}

export function useReissueEmployeeActivation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ employee, reason }: { employee: Employee; reason: string }) =>
      api.post<EmployeeActivation>(
        `/employees/${employee.id}/activation/reissue`,
        { reason },
        { "If-Match": String(employee.version) },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: employeesKey }),
  });
}

export function useEmployeeActivationPreview() {
  return useMutation({
    mutationFn: (employeeId: string) =>
      api.get<EmployeeActivationPreview>(`/employees/${employeeId}/activation-preview`),
  });
}
