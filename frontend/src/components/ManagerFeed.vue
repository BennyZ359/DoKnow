<script setup lang="ts">
import type { ManagerMessage } from '@/api/types'
import { fmtRelative } from '@/utils/format'

defineProps<{ messages: ManagerMessage[] }>()
</script>

<template>
  <div v-if="messages.length" class="feed">
    <div v-for="(m, i) in messages" :key="i" class="feed-item">
      <span class="feed-avatar">🐠</span>
      <div class="flex-1">
        <div class="row between">
          <span class="feed-author">AI 学习管家</span>
          <span class="muted small">{{ fmtRelative(m.at) }}</span>
        </div>
        <p class="feed-text">{{ m.message }}</p>
      </div>
    </div>
  </div>
  <p v-else class="muted small">管家正在观察你的学习数据，暂时没有新的提醒。</p>
</template>

<style scoped>
.feed {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.feed-item {
  display: flex;
  gap: 10px;
}

.feed-avatar {
  width: 32px;
  height: 32px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  background: var(--accent-soft);
  border-radius: 10px;
}

.feed-author {
  font-size: 13px;
  font-weight: 600;
}

.feed-text {
  margin-top: 2px;
  font-size: 13.5px;
  color: #3b4a66;
  line-height: 1.6;
}
</style>
