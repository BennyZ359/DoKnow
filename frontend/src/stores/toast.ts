import { ref } from 'vue'
import { defineStore } from 'pinia'

export interface Toast {
  id: number
  text: string
  kind: 'success' | 'error' | 'info'
}

let nextId = 1

/** Lightweight global toasts — API feedback without blocking the UI. */
export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])

  function push(text: string, kind: Toast['kind'], ttl: number): void {
    const id = nextId++
    toasts.value.push({ id, text, kind })
    setTimeout(() => dismiss(id), ttl)
  }

  function success(text: string): void {
    push(text, 'success', 3500)
  }

  function error(text: string): void {
    push(text, 'error', 6000)
  }

  function info(text: string): void {
    push(text, 'info', 3500)
  }

  function dismiss(id: number): void {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  return { toasts, push, success, error, info, dismiss }
})
