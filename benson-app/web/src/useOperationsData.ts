import { useEffect, useState } from "react";
import { requestHeaders } from "./api";
import { loadPortalData } from "./portalData";
import type {
  Dashboard,
  EmployeeDocument,
  EmployeeTask,
  Lead,
  NotificationSettings,
  PortalSession,
  RequestStatus,
  SpamFilter,
} from "./types";

const tokenKey = "benson-google-credential";
const emptyDashboard: Dashboard = {
  metrics: { new_leads: 0, active_jobs: 0, open_tasks: 0, unbilled_work: 0 },
  attention: [],
  schedule: [],
  jobs: [],
};

export function useOperationsData(status: string, source: string, spam: SpamFilter, query: string) {
  const [credential, setCredential] = useState(() => sessionStorage.getItem(tokenKey) ?? "");
  const [data, setData] = useState(emptyDashboard);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>("loading");
  const [portalSession, setPortalSession] = useState<PortalSession | null>(null);
  const [employeeTasks, setEmployeeTasks] = useState<EmployeeTask[]>([]);
  const [employeeDocuments, setEmployeeDocuments] = useState<EmployeeDocument[]>([]);
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null);
  const [settingsStatus, setSettingsStatus] = useState<"" | "saving" | "saved" | "error">("");

  useEffect(() => {
    if (!credential) {
      setData(emptyDashboard);
      setLeads([]);
      setNotificationSettings(null);
      setPortalSession(null);
      setEmployeeTasks([]);
      setEmployeeDocuments([]);
      setRequestStatus("auth-required");
      return;
    }
    const controller = new AbortController();
    let active = true;
    loadPortalData({ credential, query, signal: controller.signal, source, spam, status })
      .then((next) => {
        if (!active) return;
        if (next.kind === "unauthorized") {
          setData(emptyDashboard);
          setLeads([]);
          setNotificationSettings(null);
          setPortalSession(null);
          setRequestStatus("auth-required");
          return;
        }
        setPortalSession(next.session);
        if (next.kind === "employee") {
          setEmployeeTasks(next.tasks);
          setEmployeeDocuments(next.documents);
          setData(emptyDashboard);
          setLeads([]);
          setNotificationSettings(null);
          setRequestStatus("ready");
          return;
        }
        setEmployeeTasks([]);
        setEmployeeDocuments([]);
        setData(next.dashboard);
        setLeads(next.leads);
        setNotificationSettings(next.notificationSettings);
        setRequestStatus("ready");
      })
      .catch((error) => {
        if (active && error instanceof Error && error.name !== "AbortError") setRequestStatus("offline");
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [credential, query, source, spam, status]);

  const authenticate = (token: string) => {
    sessionStorage.setItem(tokenKey, token);
    setCredential(token);
  };
  const signOut = () => {
    sessionStorage.removeItem(tokenKey);
    setCredential("");
    setData(emptyDashboard);
    setLeads([]);
    setNotificationSettings(null);
    setPortalSession(null);
    setEmployeeTasks([]);
    setEmployeeDocuments([]);
    setRequestStatus("auth-required");
  };
  const setSmsEnabled = async (smsEnabled: boolean) => {
    if (!notificationSettings) return;
    const previous = notificationSettings;
    setNotificationSettings({ ...notificationSettings, sms_enabled: smsEnabled });
    setSettingsStatus("saving");
    try {
      const response = await fetch("/api/benson/v1/settings/notifications", {
        method: "PATCH",
        headers: { ...requestHeaders(credential), "content-type": "application/json" },
        body: JSON.stringify({ sms_enabled: smsEnabled }),
      });
      if (!response.ok) throw new Error("Settings update failed");
      setNotificationSettings(await response.json());
      setSettingsStatus("saved");
    } catch {
      setNotificationSettings(previous);
      setSettingsStatus("error");
    }
  };

  return {
    credential,
    data,
    leads,
    notificationSettings,
    portalSession,
    employeeTasks,
    employeeDocuments,
    requestStatus,
    settingsStatus,
    setLeads,
    setEmployeeTasks,
    setEmployeeDocuments,
    authenticate,
    signOut,
    setRequestStatus,
    setSmsEnabled,
  };
}
