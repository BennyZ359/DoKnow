<script setup lang="ts">
defineProps<{ centered?: boolean }>()
</script>

<template>
  <div class="spinner" :class="{ 'text-center': centered }" aria-label="加载中">
    <span />
    <span />
    <span />
  </div>
</template>
