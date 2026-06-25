// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Wire types for the phone-log capture API. A phone log turns a verbal, phoned,
// or chatted instruction into a structured, dispute-ready record: a canonical
// direction and channel, a clean party list, a duration, a short summary, and
// the instruction-bearing sentences pulled out of the transcript. The raw
// transcript is kept verbatim as the underlying evidence.

export type PhoneDirection = 'inbound' | 'outbound' | 'internal' | 'unknown';
export type PhoneChannel = 'phone' | 'voice_note' | 'chat' | 'other';

export interface PhoneLog {
  id: string;
  project_id: string;
  direction: PhoneDirection;
  channel: PhoneChannel;
  parties: string[];
  occurred_at: string | null;
  duration_seconds: number | null;
  transcript: string;
  summary: string;
  instructions: string[];
  word_count: number;
  audio_storage_key: string;
  status: string;
  created_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// The raw capture posted to the API. Everything except the project is optional
// and free-form: the server normalizes parties, direction, channel, duration,
// summary, and instructions before storing.
export interface PhoneLogCreate {
  project_id: string;
  raw_parties?: string;
  direction?: string;
  channel?: string;
  started_at?: string | null;
  ended_at?: string | null;
  duration_seconds?: number | null;
  transcript?: string;
  summary?: string;
  metadata?: Record<string, unknown>;
}
