// AI Agents — typed client for the /api/v1/ai-agents/* surface.

import { apiGet, apiPost } from '@/shared/lib/api';

export interface AgentDescriptor {
  name: string;
  description: string;
  system_prompt?: string;
  max_iterations: number;
  allowed_tools: string[];
}

export type AgentStepRole =
  | 'thought'
  | 'tool_call'
  | 'observation'
  | 'answer'
  | 'error';

export interface AgentStep {
  id: string;
  step_idx: number;
  role: AgentStepRole;
  content: unknown;
  token_count: number;
  created_at: string;
}

export interface AgentRun {
  id: string;
  agent_name: string;
  project_id: string | null;
  user_id: string;
  status: 'running' | 'completed' | 'failed';
  failure_reason: string | null;
  user_input: string;
  final_output: string | null;
  iterations: number;
  total_tokens: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  steps: AgentStep[];
}

export interface AgentRunListItem {
  id: string;
  agent_name: string;
  project_id: string | null;
  user_id: string;
  status: 'running' | 'completed' | 'failed';
  failure_reason: string | null;
  iterations: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRunRequest {
  agent_name: string;
  project_id?: string | null;
  user_input: string;
}

export interface AgentHealth {
  llm_configured: boolean;
  provider: string | null;
  model: string | null;
  settings_url: string;
}

export const aiAgentsApi = {
  listAgents: () => apiGet<AgentDescriptor[]>('/v1/ai-agents/agents/'),
  listRuns: (projectId?: string) =>
    apiGet<AgentRunListItem[]>(
      `/v1/ai-agents/runs/${projectId ? `?project_id=${projectId}` : ''}`,
    ),
  getRun: (runId: string) => apiGet<AgentRun>(`/v1/ai-agents/runs/${runId}`),
  startRun: (body: CreateAgentRunRequest) =>
    apiPost<AgentRun, CreateAgentRunRequest>('/v1/ai-agents/runs/', body),
  health: () => apiGet<AgentHealth>('/v1/ai-agents/health/'),
};
