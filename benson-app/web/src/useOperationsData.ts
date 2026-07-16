import { useEffect, useState } from "react";
import { leadQuery, requestHeaders } from "./api";
import type { Dashboard, Lead, NotificationSettings, RequestStatus, SpamFilter } from "./types";

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
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null);
  const [settingsStatus, setSettingsStatus] = useState<"" | "saving" | "saved" | "error">("");

  useEffect(() => {
    if (!credential) {
      setData(emptyDashboard);
      setLeads([]);
      setNotificationSettings(null);
      setRequestStatus("auth-required");
      return;
    }
    const controller = new AbortController();
    let active = true;
    const headers = requestHeaders(credential);
    Promise.all([
      fetch("/api/v1/dashboard", { headers, signal: controller.signal }),
      fetch(`/api/benson/v1/leads?${leadQuery(status, source, spam, query)}`, {
        headers,
        signal: controller.signal,
      }),
      fetch("/api/benson/v1/settings/notifications", { headers, signal: controller.signal }),
    ])
      .then(async ([dashboardResponse, leadsResponse, settingsResponse]) => {
        if (!active) return;
        if ([dashboardResponse, leadsResponse].some((response) => [401, 403].includes(response.status))) {
          setData(emptyDashboard);
          setLeads([]);
          setNotificationSettings(null);
          setRequestStatus("auth-required");
          return;
        }
        if (!dashboardResponse.ok || !leadsResponse.ok) throw Error("Operations API unavailable");
        const [nextData, nextLeads, nextSettings] = await Promise.all([
          dashboardResponse.json(),
          leadsResponse.json(),
          settingsResponse.ok ? settingsResponse.json() : Promise.resolve(null),
        ]);
        if (!active) return;
        setData(nextData);
        setLeads(nextLeads.leads);
        setNotificationSettings(nextSettings);
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
    requestStatus,
    settingsStatus,
    setLeads,
    authenticate,
    signOut,
    setRequestStatus,
    setSmsEnabled,
  };
}
