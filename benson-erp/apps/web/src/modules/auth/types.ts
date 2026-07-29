export type EmployeeActivationInspection = {
  employee_name: string;
  company_email: string;
  organization_name: string;
  expires_at: string;
};

export type EmployeeActivationCompletion = {
  activated: true;
  organization: string;
  email: string;
};
