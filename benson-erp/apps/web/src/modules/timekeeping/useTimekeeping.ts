import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, getAuthScope } from "../../api/client";
import type { Project } from "../scheduling/types";
import type { FederalChargeCode } from "../federal-labor/types";
import { createClientOperationId } from "./clientOperationId";
import {
  listTimeOperations,
  queueTimeOperation,
  removeTimeOperation,
} from "./offlineQueue";
import type {
  QueuedTimeOperation,
  TimeEntry,
  TimeEntryEmployeeOption,
  TimeFormFields,
} from "./types";

function dateRange() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 14);
  return { from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10) };
}

export function useTimeResources() {
  const permissions = getAuthScope()?.permissions ?? [];
  const employees = useQuery({
    queryKey: ["time-entry-employee-options"],
    queryFn: () => api.get<TimeEntryEmployeeOption[]>("/time-entries/resources/employees"),
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get<Project[]>("/projects"),
    enabled: permissions.includes("projects.read"),
  });
  const federalChargeCodes = useQuery({
    queryKey: ["federal-labor", "charge-codes"],
    queryFn: () => api.get<FederalChargeCode[]>("/federal-labor/charge-codes"),
    enabled: permissions.includes("federal_labor.charge_codes_read"),
  });
  return { employees, projects, federalChargeCodes };
}

export function useTimeEntries() {
  const range = dateRange();
  return useQuery({
    queryKey: ["time-entries", range.from, range.to],
    queryFn: () =>
      api.get<TimeEntry[]>(
        `/time-entries?date_from=${range.from}&date_to=${range.to}`,
      ),
  });
}

export function useOfflineTimeSync() {
  const client = useQueryClient();
  const [queued, setQueued] = useState<QueuedTimeOperation[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [online, setOnline] = useState(() => navigator.onLine);
  const refresh = useCallback(async () => {
    const scope = requireScope();
    setQueued(await listTimeOperations(scope.tenant_id, scope.user_id));
  }, []);
  const flush = useCallback(async () => {
    if (!navigator.onLine) return;
    setSyncing(true);
    try {
      const scope = requireScope();
      for (const operation of await listTimeOperations(scope.tenant_id, scope.user_id)) {
        await api.post<TimeEntry>("/time-entries", operation.payload);
        await removeTimeOperation(operation.id);
      }
      await client.invalidateQueries({ queryKey: ["time-entries"] });
      await refresh();
    } finally {
      setSyncing(false);
    }
  }, [client, refresh]);

  useEffect(() => {
    const initialization = window.setTimeout(() => void refresh(), 0);
    const handleOnline = () => {
      setOnline(true);
      void flush();
    };
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.clearTimeout(initialization);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [flush, refresh]);
  return { online, queued, syncing, refresh, flush };
}

export function useCreateTimeEntry(sync: ReturnType<typeof useOfflineTimeSync>) {
  const client = useQueryClient();
  return useMutation({
    networkMode: "always",
    mutationFn: async ({ fields, offline }: TimeEntrySubmission) => {
      const operation = buildOperation(fields, offline ? "OFFLINE" : "WEB");
      if (offline) {
        await queueTimeOperation(operation);
        await sync.refresh();
        return null;
      }
      try {
        return await api.post<TimeEntry>("/time-entries", operation.payload);
      } catch (error) {
        if (error instanceof ApiError) throw error;
        await queueTimeOperation(operation);
        await sync.refresh();
        return null;
      }
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["time-entries"] }),
  });
}

type TimeEntrySubmission = {
  fields: TimeFormFields;
  offline: boolean;
};

export function useTimeTransition(action: "certify" | "approve") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (entry: TimeEntry) =>
      api.post<TimeEntry>(
        `/time-entries/${entry.id}/${action}`,
        action === "certify"
          ? { statement: "I certify this record accurately reflects all hours I worked." }
          : { reason: "Supervisor verified the work and charge allocation." },
        { "If-Match": String(entry.version) },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["time-entries"] }),
  });
}

function buildOperation(
  fields: TimeFormFields,
  source: "WEB" | "OFFLINE",
): QueuedTimeOperation {
  const id = createClientOperationId();
  const scope = requireScope();
  return {
    id,
    created_at: new Date().toISOString(),
    tenant_id: scope.tenant_id,
    user_id: scope.user_id,
    payload: {
      employee_id: fields.employee_id || null,
      project_id: fields.project_id || null,
      federal_charge_code_id: fields.federal_charge_code_id || null,
      contract_code: fields.contract_code || null,
      task_order: fields.task_order || null,
      clin: fields.clin || null,
      funding_line: fields.funding_line || null,
      work_date: fields.work_date,
      start_at: new Date(`${fields.work_date}T${fields.start_time}`).toISOString(),
      end_at: new Date(`${fields.work_date}T${fields.end_time}`).toISOString(),
      break_minutes: fields.break_minutes,
      regular_hours: fields.regular_hours,
      overtime_hours: fields.overtime_hours,
      double_time_hours: fields.double_time_hours,
      travel_hours: fields.travel_hours,
      leave_hours: 0,
      indirect_hours: fields.indirect_hours,
      uncompensated_overtime_hours: 0,
      charge_code: fields.charge_code,
      cost_code: fields.cost_code || null,
      labor_category: fields.labor_category || null,
      trade: fields.trade || null,
      location: fields.location || null,
      description: fields.description,
      source,
      client_operation_id: id,
      device_id: navigator.userAgent,
      original_device_timestamp: new Date().toISOString(),
    },
  };
}

function requireScope() {
  const scope = getAuthScope();
  if (!scope) throw new ApiError(401, "Authenticated tenant scope is unavailable");
  return scope;
}
