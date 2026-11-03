import type { FullNote, Goal } from './api'
import { removeSaved } from './persistence'
import type { PendingWrite } from './writes'
import { acknowledgeWrite, pendingWrites } from './writes'

export type EditTarget = { kind: 'goals' | 'knowledge'; id: string }
export type EditableRecord = Goal | FullNote
export interface EditDraft extends Record<string, string | number> {
  version: number
  title: string
  content: string
  tags: string
  motivation: string
  daily_minutes: number
}

export const editScope = (target: EditTarget) => `edit:${target.kind}:${target.id}`
export const parseTags = (value: string) =>
  value
    .split(/[,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean)
export const sameDraft = (left: unknown, right: unknown) =>
  JSON.stringify(left) === JSON.stringify(right)

export function draftFromRecord(record: EditableRecord): EditDraft {
  return {
    version: record.version,
    title: record.title,
    content: 'content' in record ? record.content : '',
    tags: 'tags' in record ? record.tags.join(', ') : '',
    motivation: 'motivation' in record ? record.motivation : '',
    daily_minutes: 'daily_minutes' in record ? record.daily_minutes : 30,
  }
}

export function validEditDraft(value: unknown): value is EditDraft {
  if (!value || typeof value !== 'object') return false
  const draft = value as EditDraft
  return (
    Number.isInteger(draft.version) &&
    draft.version >= 1 &&
    ['title', 'content', 'tags', 'motivation'].every((key) => typeof draft[key] === 'string') &&
    typeof draft.daily_minutes === 'number' &&
    Number.isFinite(draft.daily_minutes)
  )
}

export function editPayload(target: EditTarget, draft: EditDraft, baseline?: EditableRecord) {
  const fields =
    target.kind === 'knowledge'
      ? { title: draft.title, content: draft.content, tags: parseTags(draft.tags) }
      : { title: draft.title, motivation: draft.motivation, daily_minutes: draft.daily_minutes }
  const previous: Record<string, unknown> = { ...baseline }
  // Send changed fields only, so tagging a short imported document does not
  // require rewriting its otherwise valid original title or extracted body.
  return {
    version: draft.version,
    ...Object.fromEntries(
      Object.entries(fields).filter(([key, value]) => !baseline || !sameDraft(value, previous[key]))
    ),
  }
}

export function clearEditDraft(entry: PendingWrite) {
  if (entry.draft) removeSaved('draft:' + entry.scope, (value) => sameDraft(value, entry.draft))
}

export function forgetRecordEdits(target: EditTarget) {
  const scope = editScope(target)
  removeSaved('draft:' + scope, () => true)
  for (const entry of [...pendingWrites.value]) {
    if (entry.scope === scope) acknowledgeWrite(entry)
  }
}
