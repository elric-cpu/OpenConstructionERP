import { BellRing } from "lucide-react";
import type { NotificationSettings } from "./types";

export function NotificationSettingsPanel({
  settings,
  status,
  onChange,
}: {
  settings: NotificationSettings;
  status: "" | "saving" | "saved" | "error";
  onChange(enabled: boolean): void;
}) {
  return (
    <section className="notification-settings" id="notification-settings" aria-label="Notifications settings">
      <div className="settings-icon">
        <BellRing />
      </div>
      <div>
        <small>OWNER SETTINGS</small>
        <h2>Lead notifications</h2>
        <p>
          Email alerts stay on. Twilio SMS acknowledgements and emergency alerts are optional and are currently{" "}
          {settings.sms_enabled ? "on" : "off"}.
        </p>
      </div>
      <label className="toggle-setting">
        <input
          type="checkbox"
          checked={settings.sms_enabled}
          disabled={!settings.sms_configured || status === "saving"}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>Client SMS/MMS and emergency alerts</span>
        <small>{settingLabel(settings.sms_configured, status)}</small>
      </label>
      {status === "error" && <p className="form-error">Notification settings were not saved.</p>}
    </section>
  );
}

function settingLabel(configured: boolean, status: "" | "saving" | "saved" | "error") {
  if (!configured) return "Configure Twilio before enabling";
  if (status === "saving") return "Saving…";
  if (status === "saved") return "Saved";
  return "Twilio configured";
}
