import { z } from "zod";

export const workflowSchema = z.object({
  contactName: z.string().min(1),
  email: z.email(),
  phone: z.string(),
  source: z.string().min(1),
  summary: z.string().min(1),
  qualificationReason: z.string().min(1),
  address: z.string().min(1),
  city: z.string().min(1),
  state: z.string().length(2),
  postalCode: z.string().min(5),
  pricingMode: z.enum(["MARKUP", "MARGIN"]),
  pricingRate: z.coerce.number().min(0).max(99),
  taxRate: z.coerce.number().min(0).max(100),
  sectionTitle: z.string().min(1),
  lineDescription: z.string().min(1),
  quantity: z.coerce.number().positive(),
  unit: z.string().min(1),
  unitCost: z.coerce.number().min(0),
  costCategory: z.enum(["LABOR", "MATERIAL", "EQUIPMENT", "SUBCONTRACTOR", "OTHER"]),
  projectName: z.string().min(1),
  projectNumber: z.string().min(1),
  contractNumber: z.string().min(1),
  proposalConsent: z.boolean(),
});

export type WorkflowFields = z.infer<typeof workflowSchema>;
