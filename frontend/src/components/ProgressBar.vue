<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  /** 0..1 */
  value: number | null | undefined
}>()

const pct = computed(() => Math.max(0, Math.min(100, Math.round((props.value ?? 0) * 100))))
</script>

<template>
  <div class="progress" role="progressbar" :aria-valuenow="pct">
    <div class="progress-fill" :style="{ width: pct + '%' }" />
  </div>
</template>
