import type { ReactNode } from "react";

export function Panel({
  title,
  subtitle,
  link,
  children,
}: {
  title: string;
  subtitle: string;
  link: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        <a href="#details">{link}</a>
      </div>
      {children}
    </section>
  );
}

export function Empty({
  icon,
  title,
  body,
  compact = false,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  compact?: boolean;
}) {
  return (
    <div className={`empty ${compact ? "compact" : ""}`}>
      {icon}
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}
