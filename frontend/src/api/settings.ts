import { http } from './client'

/** Generic OpenAI-compatible model config the user can set from the UI. */
export interface LlmOverride {
  provider?: string
  base_url?: string
  api_key?: string
  model?: string
}

export interface LlmSettingsResponse {
  ok: boolean
  configured: boolean
  fields: Record<string, unknown>
}

/** /settings/llm — instance-wide model override (auth required). */
export const settingsApi = {
  getLlm: () => http.get<LlmSettingsResponse>('/settings/llm'),
  updateLlm: (cfg: LlmOverride) => http.put<LlmSettingsResponse>('/settings/llm', cfg),
  clearLlm: () => http.delete<LlmSettingsResponse>('/settings/llm'),
}

/**
 * Normalize a user-entered Base URL. The OpenAI SDK appends `/chat/completions`
 * itself, so a Base URL that already ends with it (a very common mistake) would
 * double the path and 404. Strip those suffixes and any trailing slash.
 */
export function normalizeBaseUrl(url: string): string {
  return url
    .trim()
    .replace(/\/(chat\/completions|completions|embeddings|models)\/?$/i, '')
    .replace(/\/+$/, '')
}
