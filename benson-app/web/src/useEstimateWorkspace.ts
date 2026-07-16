import { useEffect, useState } from "react";
import { requestHeaders } from "./api";
import type { EstimateDraft } from "./EstimateForm";
import type { Estimate } from "./types";

export function useEstimateWorkspace(credential: string) {
  const [estimates, setEstimates] = useState<Estimate[]>([]);
  const [status, setStatus] = useState("loading");
  const headers = { ...requestHeaders(credential), "content-type": "application/json" };
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/benson/v1/estimates", { headers: requestHeaders(credential), signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Estimate API unavailable");
        setEstimates((await response.json()) as Estimate[]);
        setStatus("");
      })
      .catch((error) => {
        if (error instanceof Error && error.name !== "AbortError") setStatus("Unable to load estimates.");
      });
    return () => controller.abort();
  }, [credential]);
  const save = async (draft: EstimateDraft, editing: Estimate | null) => {
    setStatus("saving");
    const response = await fetch(editing ? `/api/benson/v1/estimates/${editing.id}` : "/api/benson/v1/estimates", {
      method: editing ? "PATCH" : "POST",
      headers,
      body: JSON.stringify(draft),
    });
    if (!response.ok) {
      setStatus("Unable to save estimate.");
      return false;
    }
    const saved = (await response.json()) as Estimate;
    setEstimates((current) =>
      editing ? current.map((item) => (item.id === saved.id ? saved : item)) : [saved, ...current],
    );
    setStatus(editing ? "Estimate changes saved." : "Estimate draft saved.");
    return true;
  };
  const transition = async (estimate: Estimate, target: Estimate["status"]) => {
    const delivered = target !== "sent" || window.confirm("Confirm this estimate was delivered outside the ERP.");
    if (!delivered) return;
    const note = ["accepted", "declined", "void"].includes(target)
      ? window.prompt("Record the factual reason for this decision:")
      : "";
    if (["accepted", "declined", "void"].includes(target) && !note?.trim()) return;
    const response = await fetch(`/api/benson/v1/estimates/${estimate.id}/transition`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        status: target,
        external_delivery_confirmed: delivered && target === "sent",
        note: note || "",
      }),
    });
    if (!response.ok) {
      setStatus("Unable to change estimate status.");
      return;
    }
    const changed = (await response.json()) as Estimate;
    setEstimates((current) => current.map((item) => (item.id === changed.id ? changed : item)));
    setStatus(`Estimate marked ${changed.status}.`);
  };
  return { estimates, save, status, transition };
}
