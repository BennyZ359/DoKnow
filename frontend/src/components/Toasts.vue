<script setup lang="ts">
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
</script>

<template>
  <transition-group name="toast" tag="div" class="toast-area">
    <div
      v-for="t in toast.toasts"
      :key="t.id"
      class="toast"
      :class="`toast-${t.kind}`"
      role="status"
      @click="toast.dismiss(t.id)"
    >
      <span class="toast-dot" />
      <span class="toast-text">{{ t.text }}</span>
    </div>
  </transition-group>
</template>
