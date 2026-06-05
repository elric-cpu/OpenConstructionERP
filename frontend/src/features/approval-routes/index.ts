// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Public surface of the Approval Routes feature.

export { ApprovalRoutesPage } from './ApprovalRoutesPage';
export { ApprovalInstanceCard } from './ApprovalInstanceCard';
export type { ApprovalInstanceCardProps } from './ApprovalInstanceCard';
export { ApprovalInstancesList } from './ApprovalInstancesList';
export { ApprovalInstanceDetailDrawer } from './ApprovalInstanceDetailDrawer';
export type { ApprovalInstanceDetailDrawerProps } from './ApprovalInstanceDetailDrawer';
export { RouteEditor } from './RouteEditor';
export * as approvalRoutesApi from './api';
export type {
  ApprovalRoute,
  ApprovalRouteCreatePayload,
  ApprovalRouteUpdatePayload,
  ApprovalRoutesMeta,
  ApprovalInstance,
  InstanceCreatePayload,
  InstanceDecidePayload,
  InstanceCancelPayload,
  InstanceStatus,
  RouteStep,
  RouteStepMode,
  RouteStepPayload,
  StepState,
  StepDecision,
  StepDecisionState,
} from './types';
