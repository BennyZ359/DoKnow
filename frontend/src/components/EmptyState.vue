<script setup lang="ts">
defineProps<{
  icon?: string
  title: string
  hint?: string
}>()
</script>

<template>
  <div class="empty">
    <div class="empty-icon">{{ icon ?? '🐟' }}</div>
    <div class="empty-title">{{ title }}</div>
    <div v-if="hint" class="empty-hint">{{ hint }}</div>
    <div class="empty-action">
      <slot />
    </div>
  </div>
</template>
