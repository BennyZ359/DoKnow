import { ref, watch } from 'vue'

type Fields = Record<string, string | number>
const prefix = 'doknow:v1:'
const memory = new Map<string, unknown>()
export const storageWarning = ref('')

function warn() {
  storageWarning.value =
    '浏览器暂时无法完整保存草稿。当前文字仍在，请先复制重要内容；关闭页面后可能无法恢复。'
}

// A per-tab shadow keeps another open tab from replacing this tab's draft.
// localStorage supplies the most recently saved draft when opening a new tab.
export function readSaved<T>(key: string, valid: (value: unknown) => value is T): T | null {
  if (memory.has(key)) return memory.get(key) as T
  for (const name of ['sessionStorage', 'localStorage'] as const) {
    try {
      const raw = window[name].getItem(prefix + key)
      if (raw === null) continue
      const value: unknown = JSON.parse(raw)
      if (valid(value)) {
        memory.set(key, value)
        return value
      }
      storageWarning.value =
        '有一份本地草稿无法读取。你现在输入的内容会另行保存，请检查需要恢复的文字。'
    } catch {
      warn()
    }
  }
  return null
}

export function saveValue(key: string, value: unknown) {
  memory.set(key, value)
  for (const name of ['sessionStorage', 'localStorage'] as const) {
    try {
      window[name].setItem(prefix + key, JSON.stringify(value))
    } catch {
      warn()
    }
  }
}

export function removeSaved(key: string, matches: (value: unknown) => boolean) {
  if (matches(memory.get(key))) memory.delete(key)
  for (const name of ['sessionStorage', 'localStorage'] as const) {
    try {
      const raw = window[name].getItem(prefix + key)
      if (raw !== null && matches(JSON.parse(raw))) window[name].removeItem(prefix + key)
    } catch {
      warn()
    }
  }
}

export function savedKeys(kind: string): string[] {
  const keys = new Set([...memory.keys()].filter((key) => key.startsWith(kind)))
  for (const name of ['sessionStorage', 'localStorage'] as const) {
    try {
      const storage = window[name]
      for (let index = 0; index < storage.length; index++) {
        const key = storage.key(index)
        if (key?.startsWith(prefix + kind)) keys.add(key.slice(prefix.length))
      }
    } catch {
      warn()
    }
  }
  return [...keys]
}

const same = (first: unknown, second: unknown) => JSON.stringify(first) === JSON.stringify(second)

export function useDrafts() {
  const bindings: {
    scope: () => string | null
    current: () => Fields
    reset: () => void
  }[] = []

  function bind(scope: () => string | null, current: () => Fields, apply: (value: Fields) => void) {
    const empty = { ...current() }
    let restoring = false
    const reset = () => {
      restoring = true
      apply({ ...empty })
      restoring = false
    }
    const valid = (value: unknown): value is Fields => {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return false
      return Object.keys(empty).every((key) => {
        const item = (value as Fields)[key]
        return (
          typeof item === typeof empty[key] && (typeof item !== 'number' || Number.isFinite(item))
        )
      })
    }
    watch(
      scope,
      (key) => {
        restoring = true
        const saved = key ? readSaved('draft:' + key, valid) : null
        apply(
          Object.fromEntries(
            Object.keys(empty).map((field) => [field, saved?.[field] ?? empty[field]])
          )
        )
        restoring = false
      },
      { immediate: true, flush: 'sync' }
    )
    watch(
      current,
      (value) => {
        const key = scope()
        if (key && !restoring) saveValue('draft:' + key, { ...value })
      },
      { deep: true, flush: 'sync' }
    )
    bindings.push({ scope, current, reset })
  }

  function clearSubmitted(scope: string, submitted: unknown) {
    removeSaved('draft:' + scope, (value) => same(value, submitted))
    for (const binding of bindings) {
      if (binding.scope() === scope && same(binding.current(), submitted)) binding.reset()
    }
  }

  function removeUnits(ids: string[]) {
    const scopes = ids.map((id) => `unit:${id}:`)
    for (const key of savedKeys('draft:unit:')) {
      if (scopes.some((scope) => key.startsWith('draft:' + scope))) removeSaved(key, () => true)
    }
    for (const binding of bindings) {
      if (scopes.some((scope) => binding.scope()?.startsWith(scope))) binding.reset()
    }
  }

  return { bind, clearSubmitted, removeUnits }
}
