import { leadQuery, requestHeaders } from "./api";
import type {
  Dashboard,
  Customer,
  EmployeeDocument,
  EmployeeTask,
  Lead,
  NotificationSettings,
  PortalSession,
  SpamFilter,
} from "./types";

type EmployeePortalData = {
  kind: "employee";
  session: PortalSession;
  tasks: EmployeeTask[];
  documents: EmployeeDocument[];
};
type StaffPortalData = {
  kind: "staff";
  session: PortalSession;
  dashboard: Dashboard;
  leads: Lead[];
  customers: Customer[];
  notificationSettings: NotificationSettings | null;
};
type UnauthorizedPortalData = { kind: "unauthorized" };
export type PortalData = EmployeePortalData | StaffPortalData | UnauthorizedPortalData;

export async function loadPortalData({
  credential,
  query,
  signal,
  source,
  spam,
  status,
}: {
  credential: string;
  query: string;
  signal: AbortSignal;
  source: string;
  spam: SpamFilter;
  status: string;
}): Promise<PortalData> {
  const headers = requestHeaders(credential);
  const sessionResponse = await fetch("/api/benson/v1/session", { headers, signal });
  const session: PortalSession | null = sessionResponse.ok ? await sessionResponse.json() : null;
  if (session?.kind === "employee") {
    const [tasksResponse, documentsResponse] = await Promise.all([
      fetch("/api/benson/v1/onboarding/tasks", { headers, signal }),
      fetch("/api/benson/v1/onboarding/documents", { headers, signal }),
    ]);
    if ([tasksResponse, documentsResponse].some((response) => [401, 403].includes(response.status))) {
      return { kind: "unauthorized" };
    }
    if (!tasksResponse.ok || !documentsResponse.ok) throw new Error("Onboarding API unavailable");
    const [tasksPayload, documents] = await Promise.all([
      tasksResponse.json() as Promise<{ tasks: EmployeeTask[] }>,
      documentsResponse.json() as Promise<EmployeeDocument[]>,
    ]);
    return { kind: "employee", session, tasks: tasksPayload.tasks, documents };
  }
  const [dashboardResponse, leadsResponse, customersResponse, settingsResponse] = await Promise.all([
    fetch("/api/v1/dashboard", { headers, signal }),
    fetch(`/api/benson/v1/leads?${leadQuery(status, source, spam, query)}`, { headers, signal }),
    fetch(`/api/benson/v1/customers?query=${encodeURIComponent(query)}`, { headers, signal }),
    fetch("/api/benson/v1/settings/notifications", { headers, signal }),
  ]);
  if ([dashboardResponse, leadsResponse].some((response) => [401, 403].includes(response.status))) {
    return { kind: "unauthorized" };
  }
  if (!dashboardResponse.ok || !leadsResponse.ok || !customersResponse.ok)
    throw new Error("Operations API unavailable");
  const [dashboard, leadsPayload, customers, notificationSettings] = await Promise.all([
    dashboardResponse.json() as Promise<Dashboard>,
    leadsResponse.json() as Promise<{ leads: Lead[] }>,
    customersResponse.json() as Promise<Customer[]>,
    settingsResponse.ok ? (settingsResponse.json() as Promise<NotificationSettings>) : Promise.resolve(null),
  ]);
  return {
    kind: "staff",
    session: session ?? { kind: "staff", email: "", role: "office", default_view: "overview", employee: null },
    dashboard,
    leads: leadsPayload.leads,
    customers,
    notificationSettings,
  };
}
