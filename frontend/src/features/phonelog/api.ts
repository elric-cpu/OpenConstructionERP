// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// API client for phone-log capture. The create path posts a raw, free-form
// capture; the server normalizes it (parties, direction, channel, duration,
// summary, extracted instructions) and returns the canonical record.

import { apiGet, apiPost } from '@/shared/lib/api';
import type { PhoneLog, PhoneLogCreate } from './types';

const BASE = '/v1/phonelog';

export function listPhoneLogs(
  projectId: string,
  opts?: { direction?: string; channel?: string },
): Promise<PhoneLog[]> {
  const params = new URLSearchParams({ project_id: projectId });
  if (opts?.direction) params.set('direction', opts.direction);
  if (opts?.channel) params.set('channel', opts.channel);
  return apiGet<PhoneLog[]>(`${BASE}/?${params.toString()}`);
}

export function createPhoneLog(body: PhoneLogCreate): Promise<PhoneLog> {
  return apiPost<PhoneLog, PhoneLogCreate>(`${BASE}/`, body);
}
