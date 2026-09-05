import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./AuthContext";
import { LoginPage } from "../routes/LoginPage";
import { LeadToProjectPage } from "../routes/LeadToProjectPage";
import { EmployeesPage } from "../routes/EmployeesPage";
import { SecurityPage } from "../routes/SecurityPage";
import { SchedulePage } from "../routes/SchedulePage";
import { TimekeepingPage } from "../routes/TimekeepingPage";
import { PayrollPage } from "../routes/PayrollPage";
import { FederalLaborPage } from "../routes/FederalLaborPage";
import { ActivationPage } from "../routes/ActivationPage";

export function App() {
  const auth = useAuth();
  const activating = window.location.pathname === "/activate";
  if (auth.initializing && !activating) {
    return <main className="centered min-h-screen">Restoring your secure session…</main>;
  }
  return (
    <Routes>
      <Route path="/activate" element={<ActivationPage />} />
      <Route
        path="/login"
        element={auth.authenticated ? <Navigate to="/sales/new" replace /> : <LoginPage />}
      />
      <Route
        path="/sales/new"
        element={auth.authenticated ? <LeadToProjectPage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/settings/security"
        element={auth.authenticated ? <SecurityPage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/employees"
        element={auth.authenticated ? <EmployeesPage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/schedule"
        element={auth.authenticated ? <SchedulePage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/time"
        element={auth.authenticated ? <TimekeepingPage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/payroll"
        element={auth.authenticated ? <PayrollPage /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/federal-labor"
        element={auth.authenticated ? <FederalLaborPage /> : <Navigate to="/login" replace />}
      />
      <Route path="*" element={<Navigate to={auth.authenticated ? "/sales/new" : "/login"} />} />
    </Routes>
  );
}
