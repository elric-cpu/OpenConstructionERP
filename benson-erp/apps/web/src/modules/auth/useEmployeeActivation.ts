import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { EmployeeActivationCompletion, EmployeeActivationInspection } from "./types";

export function useInspectEmployeeActivation(token: string) {
  return useQuery({
    queryKey: ["employee-activation", "inspect", token],
    queryFn: () =>
      api.post<EmployeeActivationInspection>("/auth/employee-activations/inspect", { token }),
    enabled: Boolean(token),
    retry: false,
  });
}

export function useCompleteEmployeeActivation() {
  return useMutation({
    mutationFn: (input: { token: string; password: string }) =>
      api.post<EmployeeActivationCompletion>("/auth/employee-activations/complete", input),
  });
}
