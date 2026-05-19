import { useState, useCallback, useRef, useEffect } from 'react';
import { useAuthStore } from '@/stores/useAuthStore';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { aiApi, type AISettings } from '@/features/ai/api';
import type { ChatMessage, DataPanelEntry, ToolCallInfo } from '../types';

const DEFAULT_SUGGESTIONS = [
  'Show all projects',
  'BOQ overview for this project',
  'Run validation',
  'Risk overview',
  'Search CWICR database',
];

function uid(): string {
  return crypto.randomUUID?.() ?? Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export interface UseChatFullPageReturn {
  messages: ChatMessage[];
  isStreaming: boolean;
  sessionId: string | null;
  suggestions: string[];
  dataPanelEntries: DataPanelEntry[];
  activePanelIndex: number;
  aiConfigured: boolean | null; // null = still loading
  sendMessage: (text: string) => void;
  clearChat: () => void;
  setActivePanelIndex: (idx: number) => void;
}

export function useChatFullPage(): UseChatFullPageReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS);
  const [dataPanelEntries, setDataPanelEntries] = useState<DataPanelEntry[]>([]);
  const [activePanelIndex, setActivePanelIndex] = useState(-1);
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);

  // Check if any AI provider is configured
  useEffect(() => {
    let cancelled = false;
    aiApi
      .getSettings()
      .then((settings: AISettings) => {
        if (cancelled) return;
        const hasKey =
          settings.anthropic_api_key_set ||
          settings.openai_api_key_set ||
          settings.gemini_api_key_set ||
          settings.openrouter_api_key_set ||
          settings.mistral_api_key_set ||
          settings.groq_api_key_set ||
          settings.deepseek_api_key_set ||
          settings.cohere_api_key_set;
        setAiConfigured(hasKey);
      })
      .catch(() => {
        if (!cancelled) setAiConfigured(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      // If no AI provider is configured, show an onboarding message instead
      // of hitting the API (which would return a 500 error).
      if (aiConfigured === false) {
        const userMsg: ChatMessage = {
          id: uid(),
          role: 'user',
          content: trimmed,
          ts: new Date(),
        };
        const onboardingMsg: ChatMessage = {
          id: uid(),
          role: 'assistant',
          content:
            '**AI assistant is not configured yet**\n\n' +
            'Connect your AI provider (Anthropic, OpenAI, Google, or another supported provider) in **Settings** to enable the chat assistant.\n\n' +
            'Go to [Settings](/settings) to add your API key.',
          ts: new Date(),
        };
        setMessages((prev) => [...prev, userMsg, onboardingMsg]);
        return;
      }

      const userMsg: ChatMessage = {
        id: uid(),
        role: 'user',
        content: trimmed,
        ts: new Date(),
      };
      const aiMsg: ChatMessage = {
        id: uid(),
        role: 'assistant',
        content: '',
        toolCalls: [],
        ts: new Date(),
      };

      setMessages((prev) => [...prev, userMsg, aiMsg]);
      setIsStreaming(true);
      setSuggestions([]);

      const token = useAuthStore.getState().accessToken;

      const controller = new AbortController();
      abortRef.current = controller;

      const aiMsgId = aiMsg.id;

      (async () => {
        try {
          const response = await fetch('/api/v1/erp_chat/stream/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
              message: trimmed,
              session_id: sessionId,
              project_id: activeProjectId,
            }),
            signal: controller.signal,
          });

          if (!response.ok) {
            const errText = await response.text().catch(() => 'Unknown error');
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiMsgId ? { ...m, content: `Error: ${response.status} - ${errText}` } : m,
              ),
            );
            setIsStreaming(false);
            return;
          }

          const reader = response.body?.getReader();
          if (!reader) {
            setIsStreaming(false);
            return;
          }

          const decoder = new TextDecoder();
          let buffer = '';
          // The backend emits standard SSE frames where the event name is on
          // an ``event:`` line and the JSON payload on the following
          // ``data:`` line (see backend _sse()). The previous parser only
          // read ``data:`` and switched on a non-existent ``chunk.type``
          // field, so NOTHING ever rendered. Track the current event name
          // and reset it after each blank-line-delimited frame.
          let currentEvent = '';

          const lastToolCallId = { id: '' };

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            // Keep the last (possibly incomplete) line in the buffer
            buffer = lines.pop() ?? '';

            for (const rawLine of lines) {
              const line = rawLine.replace(/\r$/, '');
              // Blank line terminates an SSE frame — reset the event name.
              if (line.trim() === '') {
                currentEvent = '';
                continue;
              }
              if (line.startsWith('event:')) {
                currentEvent = line.slice(6).trim();
                continue;
              }
              if (!line.startsWith('data:')) continue;

              const jsonStr = line.slice(5).trim();
              if (!jsonStr || jsonStr === '[DONE]') continue;

              let payload: Record<string, unknown>;
              try {
                payload = JSON.parse(jsonStr) as Record<string, unknown>;
              } catch {
                continue;
              }

              switch (currentEvent) {
                case 'session_id': {
                  const sid = payload.session_id as string | undefined;
                  if (sid) setSessionId(sid);
                  break;
                }

                case 'text': {
                  const content = payload.content as string | undefined;
                  if (content) {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === aiMsgId
                          ? { ...m, content: m.content + content }
                          : m,
                      ),
                    );
                  }
                  break;
                }

                case 'tool_start': {
                  const toolName = (payload.tool as string | undefined) ?? 'unknown';
                  const toolCall: ToolCallInfo = {
                    id: uid(),
                    name: toolName,
                    status: 'running',
                    input: payload.args as Record<string, unknown> | undefined,
                    startedAt: Date.now(),
                  };
                  lastToolCallId.id = toolCall.id;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === aiMsgId
                        ? { ...m, toolCalls: [...(m.toolCalls ?? []), toolCall] }
                        : m,
                    ),
                  );
                  break;
                }

                case 'tool_result': {
                  // Backend payload: { tool, result }. There is no per-call
                  // id on the wire, so the most-recently-started running
                  // tool call for this message is the one being resolved.
                  const result = payload.result as ToolCallInfo['result'] | undefined;
                  setMessages((prev) =>
                    prev.map((m) => {
                      if (m.id !== aiMsgId) return m;
                      let matched = false;
                      const toolCalls = (m.toolCalls ?? [])
                        .slice()
                        .reverse()
                        .map((tc) => {
                          if (!matched && tc.status === 'running') {
                            matched = true;
                            return {
                              ...tc,
                              status: 'done' as const,
                              result,
                              durationMs: Date.now() - tc.startedAt,
                            };
                          }
                          return tc;
                        })
                        .reverse();
                      return { ...m, toolCalls };
                    }),
                  );

                  // Add to data panel entries
                  if (result?.renderer) {
                    const entry: DataPanelEntry = {
                      renderer: result.renderer,
                      data: result.data,
                      toolName: (payload.tool as string | undefined) ?? 'unknown',
                      summary: result.summary ?? '',
                      timestamp: Date.now(),
                    };
                    setDataPanelEntries((prev) => [...prev, entry]);
                    setActivePanelIndex((prev) => (prev < 0 ? 0 : prev + 1));
                  }
                  break;
                }

                case 'error': {
                  const errMsg = (payload.message as string | undefined) ?? 'Unknown error';
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === aiMsgId
                        ? {
                            ...m,
                            content: m.content + `\n\n**Error:** ${errMsg}`,
                            toolCalls: (m.toolCalls ?? []).map((tc) =>
                              tc.status === 'running'
                                ? { ...tc, status: 'error' as const, durationMs: Date.now() - tc.startedAt }
                                : tc,
                            ),
                          }
                        : m,
                    ),
                  );
                  break;
                }

                case 'done': {
                  break;
                }
              }
            }
          }
        } catch (err: unknown) {
          if (err instanceof DOMException && err.name === 'AbortError') {
            // User-initiated abort
          } else {
            const errorMsg = err instanceof Error ? err.message : 'Connection failed';
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiMsgId
                  ? { ...m, content: m.content || `Error: ${errorMsg}` }
                  : m,
              ),
            );
          }
        } finally {
          setIsStreaming(false);
          abortRef.current = null;
        }
      })();
    },
    [isStreaming, sessionId, activeProjectId, aiConfigured],
  );

  const clearChat = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    setMessages([]);
    setIsStreaming(false);
    setSessionId(null);
    setSuggestions(DEFAULT_SUGGESTIONS);
    setDataPanelEntries([]);
    setActivePanelIndex(-1);
  }, []);

  return {
    messages,
    isStreaming,
    sessionId,
    suggestions,
    dataPanelEntries,
    activePanelIndex,
    aiConfigured,
    sendMessage,
    clearChat,
    setActivePanelIndex,
  };
}
