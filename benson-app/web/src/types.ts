export type RequestStatus = "loading" | "ready" | "auth-required" | "offline";
export type ActiveView = "overview" | "leads";
export type SpamFilter = "active" | "spam" | "all";
export type BusyState = "lead" | "save" | "draft" | "";

export type Dashboard = {
  metrics: Record<string, number>;
  attention: unknown[];
  schedule: unknown[];
  jobs: unknown[];
};

export type NotificationSettings = {
  email_enabled: true;
  sms_enabled: boolean;
  sms_configured: boolean;
};

export type Lead = {
  id: string;
  status: string;
  priority: string;
  name: string;
  phone: string;
  email: string | null;
  service_type: string;
  city: string;
  created_at: string;
  assigned_to: string | null;
  source: string;
  is_spam: boolean;
  spam_reason: string | null;
};

export type Attachment = {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type Note = { id: string; author: string; body: string; created_at: string };
export type AuditEvent = {
  id: string;
  event: string;
  actor: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

export type LeadDetail = Lead & {
  payload: Record<string, unknown>;
  attachments: Attachment[];
  notes: Note[];
  audit_events: AuditEvent[];
};

export type Skill = { id: string; label: string; description: string; risk: string };
export type StaffMember = { email: string; display_name: string; role: string };
export type EditableLead = {
  name: string;
  phone: string;
  email: string;
  service_type: string;
  city: string;
  source: string;
};
