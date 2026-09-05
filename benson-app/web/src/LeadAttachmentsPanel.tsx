import { Download, FileText } from "lucide-react";
import { formatBytes } from "./formatters";
import type { Attachment } from "./types";

export function LeadAttachmentsPanel({
  attachments,
  credential,
  onError,
}: {
  attachments: Attachment[];
  credential: string;
  onError(message: string): void;
}) {
  const download = async (attachment: Attachment) => {
    onError("");
    try {
      const response = await fetch(`/api/benson/v1/attachments/${attachment.id}`, {
        headers: { authorization: `Bearer ${credential}` },
      });
      if (!response.ok) throw new Error("download failed");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = attachment.original_name;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      onError("The private attachment could not be downloaded.");
    }
  };
  return (
    <section className="workspace-card">
      <div className="card-heading">
        <div>
          <small>PRIVATE FILES</small>
          <h2>Attachments</h2>
        </div>
        <Download />
      </div>
      {attachments.length ? (
        <div className="attachment-list">
          {attachments.map((attachment) => (
            <button key={attachment.id} onClick={() => void download(attachment)}>
              <FileText />
              <span>
                <strong>{attachment.original_name}</strong>
                <small>
                  {attachment.content_type} · {formatBytes(attachment.size_bytes)}
                </small>
              </span>
              <Download />
            </button>
          ))}
        </div>
      ) : (
        <p className="quiet">No customer files are attached.</p>
      )}
    </section>
  );
}
