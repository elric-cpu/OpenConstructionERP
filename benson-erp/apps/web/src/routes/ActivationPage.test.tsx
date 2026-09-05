import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { ActivationPage } from "./ActivationPage";

function renderPage(fragment = "") {
  window.history.replaceState(null, "", `/activate${fragment}`);
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter><ActivationPage /></BrowserRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

test("consumes the fragment token before inspecting the invitation", async () => {
  const fetchMock = vi.fn().mockImplementation(async () => {
    expect(window.location.hash).toBe("");
    return {
      ok: true,
      status: 200,
      json: async () => ({
        employee_name: "Taylor Reed",
        company_email: "taylor@benson.example",
        organization_name: "Benson Enterprises",
        expires_at: "2026-07-27T18:00:00Z",
      }),
    };
  });
  vi.stubGlobal("fetch", fetchMock);

  renderPage("#token=single-use-secret");

  expect(await screen.findByRole("heading", { name: "Set your ERP password" })).toBeInTheDocument();
  expect(screen.getByText("taylor@benson.example")).toBeInTheDocument();
  expect(window.location.hash).toBe("");
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/auth/employee-activations/inspect",
    expect.objectContaining({ body: JSON.stringify({ token: "single-use-secret" }) }),
  );
});

test("validates confirmation and completes activation", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        employee_name: "Taylor Reed",
        company_email: "taylor@benson.example",
        organization_name: "Benson Enterprises",
        expires_at: "2026-07-27T18:00:00Z",
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ activated: true, organization: "benson-enterprises", email: "taylor@benson.example" }),
    });
  vi.stubGlobal("fetch", fetchMock);
  renderPage("#token=single-use-secret");
  await screen.findByRole("heading", { name: "Set your ERP password" });

  fireEvent.change(screen.getByLabelText("Create password"), { target: { value: "long-safe-passphrase" } });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "different-passphrase" } });
  fireEvent.click(screen.getByRole("button", { name: "Activate account" }));
  expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);

  fireEvent.change(screen.getByLabelText(/^Confirm password/), { target: { value: "long-safe-passphrase" } });
  fireEvent.click(screen.getByRole("button", { name: "Activate account" }));
  expect(await screen.findByRole("heading", { name: "You’re all set" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("shows the same safe error for missing and rejected tokens", async () => {
  const { unmount } = renderPage();
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid or no longer available");
  unmount();

  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false,
    status: 410,
    json: async () => ({ detail: "Activation token already used" }),
  }));
  renderPage("#token=rejected-secret");
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("invalid or no longer available"));
  expect(screen.queryByText("already used")).not.toBeInTheDocument();
});
