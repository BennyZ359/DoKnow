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
