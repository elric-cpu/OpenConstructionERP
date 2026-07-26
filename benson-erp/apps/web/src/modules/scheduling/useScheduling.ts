import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../../api/client";
import type { Employee } from "../people/types";
import type {
  Activity,
  Assignment,
  Project,
  Schedule,
  ScheduleAssignmentInput,
  ScheduleEntry,
} from "./types";

function scheduleWindow() {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 14);
  return { start, end };
}

export function useScheduleResources() {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get<Project[]>("/projects"),
  });
  const employees = useQuery({
    queryKey: ["employees"],
    queryFn: () => api.get<Employee[]>("/employees"),
  });
  return { projects, employees };
}

export function useScheduleEntries() {
  const { start, end } = scheduleWindow();
  return useQuery({
    queryKey: ["schedule-entries", start.toISOString(), end.toISOString()],
    queryFn: () =>
      api.get<ScheduleEntry[]>(
        `/schedule-entries?start_at=${encodeURIComponent(start.toISOString())}&end_at=${encodeURIComponent(end.toISOString())}`,
      ),
  });
}

export function useCreateAssignment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createAssignment,
    onSuccess: () => client.invalidateQueries({ queryKey: ["schedule-entries"] }),
  });
}

async function createAssignment(input: ScheduleAssignmentInput) {
  const schedule = await ensureSchedule(input.project_id);
  const activity = await api.post<Activity>(
    `/schedules/${schedule.id}/activities`,
    {
      title: input.title,
      start_at: new Date(input.start_at).toISOString(),
      end_at: new Date(input.end_at).toISOString(),
      location: input.location || null,
      required_tools: input.required_tools || null,
    },
    { "If-Match": String(schedule.version) },
  );
  const assignment = await api.post<Assignment>(
    `/schedule-activities/${activity.id}/assignments`,
    {
      employee_id: input.employee_id,
      assignment_role: input.assignment_role || null,
      reason: "Assignment created through the manager dispatch board",
    },
    { "If-Match": String(activity.version) },
  );
  return { activity, assignment };
}

async function ensureSchedule(projectId: string) {
  try {
    return await api.get<Schedule>(`/projects/${projectId}/schedule`);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
    return api.post<Schedule>("/schedules", {
      project_id: projectId,
      name: "Construction Schedule",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
  }
}
