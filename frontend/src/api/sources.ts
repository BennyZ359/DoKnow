import { http } from './client'
import type { Source } from './types'

export interface SourceListResponse {
  sources: Source[]
}

/** ingest_upload 的返回是解析流水线的受理回执，字段较松散. */
export type UploadSourceResponse = Record<string, unknown>

export type ParseBackend = 'docling' | 'mineru'

/** /goals/{id}/sources — 参考资料上传与解析（Docling / MinerU）. */
export const sourcesApi = {
  upload: (goalId: string, file: File, backend?: ParseBackend) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<UploadSourceResponse>(`/goals/${goalId}/sources`, form, { backend })
  },
  list: (goalId: string) => http.get<SourceListResponse>(`/goals/${goalId}/sources`),
  get: (goalId: string, sourceId: string) =>
    http.get<Source>(`/goals/${goalId}/sources/${sourceId}`),
}
