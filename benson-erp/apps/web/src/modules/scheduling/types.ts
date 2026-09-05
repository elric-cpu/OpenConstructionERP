export type Project = {
  id: string;
  project_number: string;
  name: string;
  status: string;
};

export type Schedule = {
  id: string;
  project_id: string;
  name: string;
  timezone: string;
  version: number;
};

export type Activity = {
  id: string;
  schedule_id: string;
  project_id: string;
  title: string;
  description: string | null;
  start_at: string;
  end_at: string;
  status: "PLANNED" | "CONFIRMED" | "IN_PROGRESS" | "COMPLETE" | "CANCELLED";
  location: string | null;
  required_tools: string | null;
  version: number;
};

export type Assignment = {
  id: string;
  activity_id: string;
  employee_id: string;
  assignment_role: string | null;
  version: number;
};

export type ScheduleEntry = {
  activity: Activity;
  assignment: Assignment | null;
  employee_name: string | null;
  project_name: string;
};

export type ScheduleAssignmentInput = {
  project_id: string;
  employee_id: string;
  title: string;
  start_at: string;
  end_at: string;
  location: string;
  required_tools: string;
  assignment_role: string;
};
