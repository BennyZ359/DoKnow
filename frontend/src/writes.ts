import { ref } from 'vue'
import { api, ApiError } from './api'
import { readSaved, removeSaved, savedKeys, saveValue } from './persistence'

export interface PendingWrite {
  key: string
  scope: string
  path: string
  fingerprint: string
  label: string
  method?: 'POST' | 'PATCH'
  draft?: Record<string, unknown>
  payload?: Record<string, unknown>
  filename?: string
}

function valid(value: unknown): value is PendingWrite {
  if (!value || typeof value !== 'object') return false
  const entry = value as PendingWrite
  return (
    typeof entry.key === 'string' &&
    /^[A-Za-z0-9._:-]{8,128}$/.test(entry.key) &&
    typeof entry.scope === 'string' &&
    typeof entry.path === 'string' &&
    /^\/(graphs|roadmaps|goals(?:\/[a-zA-Z0-9-]+(?:\/course\/(preview|apply))?)?|knowledge(?:\/[a-zA-Z0-9-]+)?|units\/[a-zA-Z0-9-]+\/(learn|practice|project|teach|reflect|review|chat))$/.test(
      entry.path
    ) &&
    (entry.method === undefined || entry.method === 'POST' || entry.method === 'PATCH') &&
    (entry.method !== 'PATCH' || /^\/(goals|knowledge)\/[a-zA-Z0-9-]+$/.test(entry.path)) &&
    typeof entry.label === 'string' &&
    typeof entry.fingerprint === 'string' &&
    (entry.payload === undefined ||
      (!!entry.payload && typeof entry.payload === 'object' && !Array.isArray(entry.payload)))
  )
}

export const pendingWrites = ref<PendingWrite[]>(
  savedKeys('write:').flatMap((key) => {
    const entry = readSaved(key, valid)
    return entry ? [entry] : []
  })
)

function remember(entry: PendingWrite) {
  saveValue('write:' + entry.key, entry)
  pendingWrites.value = [...pendingWrites.value.filter((item) => item.key !== entry.key), entry]
}

export function acknowledgeWrite(entry: PendingWrite) {
  removeSaved('write:' + entry.key, (value) => valid(value) && value.key === entry.key)
  pendingWrites.value = pendingWrites.value.filter((item) => item.key !== entry.key)
}

export function forgetUnitWrites(ids: string[]) {
  for (const entry of [...pendingWrites.value]) {
    if (ids.some((id) => entry.scope.startsWith(`unit:${id}:`))) acknowledgeWrite(entry)
  }
}

async function digest(value: string | ArrayBuffer) {
  const data = typeof value === 'string' ? new TextEncoder().encode(value) : value
  const hash = await crypto.subtle.digest('SHA-256', data)
  return [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

export async function sendWrite<T>(
  path: string,
  payload: Record<string, unknown> | File,
  scope: string,
  label: string,
  existing?: PendingWrite,
  method: 'POST' | 'PATCH' = existing?.method || 'POST',
  draft?: Record<string, unknown>
): Promise<{ result: T; entry: PendingWrite }> {
  const isFile = payload instanceof File
  // Snapshot reactive forms before the first await; typing or navigation cannot
  // silently change the request associated with an existing key.
  const snapshot = isFile ? payload : JSON.parse(JSON.stringify(payload))
  const fingerprint = isFile
    ? await digest(payload.name + ':' + (await digest(await payload.arrayBuffer())))
    : await digest(JSON.stringify(snapshot))
  if (
    existing &&
    (existing.path !== path ||
      existing.fingerprint !== fingerprint ||
      (existing.method || 'POST') !== method)
  ) {
    throw new ApiError(
      '这份恢复记录已损坏，无法安全确认。请先同步并核对已保存的记录；原文仍然保留。'
    )
  }
  const previous =
    existing ||
    pendingWrites.value.find(
      (item) =>
        item.scope === scope &&
        item.path === path &&
        item.fingerprint === fingerprint &&
        (item.method || 'POST') === method
    )
  const entry: PendingWrite =
    previous?.path === path && previous.fingerprint === fingerprint
      ? previous
      : {
          key: crypto.randomUUID(),
          path,
          scope,
          label,
          method,
          ...(draft ? { draft: JSON.parse(JSON.stringify(draft)) } : {}),
          fingerprint,
          ...(isFile ? { filename: payload.name } : { payload: snapshot }),
        }
  remember(entry)
  const body = isFile ? new FormData() : JSON.stringify(snapshot)
  if (body instanceof FormData) body.append('file', payload as File)
  try {
    const result = await api<T>(path, {
      method,
      headers: { 'Idempotency-Key': entry.key },
      body,
    })
    // The caller clears only the submitted draft before acknowledging. A lost
    // response or reload keeps the same key until the outcome is confirmed.
    return { result, entry }
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status >= 400 &&
      error.status < 500 &&
      error.code !== 'idempotency_in_progress' &&
      error.code !== 'idempotency_expired_owner'
    ) {
      acknowledgeWrite(entry)
    }
    throw error
  }
}
