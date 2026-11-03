<script setup lang="ts">
import type { Assessment } from '../api'

defineProps<{ assessment: Assessment | null | undefined }>()
const labels = {
  demo: '体验 · 结构检查',
  ai: 'AI · 语义评价',
  answer_key: '服务端 · 答案核对',
  unknown: '来源未知',
}
</script>

<template>
  <div v-if="assessment" class="assessment-details">
    <span class="pill">{{ labels[assessment.source] || labels.unknown }}</span>
    <span v-if="assessment.passed !== undefined">
      {{ assessment.passed ? '本次检查通过' : '本次仍需巩固' }}
    </span>
    <p v-if="assessment.source === 'unknown'">
      这条历史记录未保存评价来源，无法追溯当时的模型或规则。
    </p>
    <p v-else-if="assessment.source === 'demo'">仅检查内容结构，不验证知识正确性，也不执行代码。</p>
    <p v-else-if="assessment.source === 'ai'">模型意见可能有误，请结合实际结果和可靠资料核验。</p>
    <p v-else>按照本题预设答案核对；多题通过仍需实战与延迟回忆检验。</p>
    <p v-if="assessment.source === 'ai'" class="assessment-model">
      服务：{{ assessment.provider || '未知' }} · 请求模型：{{
        assessment.requested_model || '未记录'
      }}
      · 返回模型：{{ assessment.model || '服务未提供' }}
    </p>
    <small v-if="assessment.rule_version">评价规则：{{ assessment.rule_version }}</small>
    <div v-if="assessment.question" class="question-evidence">
      <p><strong>作答题目：</strong>{{ assessment.question }}</p>
      <p>你的答案：{{ assessment.selected_answer }}</p>
      <p>参考答案：{{ assessment.correct_answer }}</p>
      <small>
        第 {{ assessment.round }} 轮 · 第 {{ assessment.attempt }} 次作答
        {{ assessment.was_retry ? '· 错题补练' : '' }} ·
        {{
          assessment.question_source?.source === 'demo'
            ? '体验题库'
            : assessment.question_source?.source === 'ai'
              ? 'AI 生成题目'
              : '题目来源未知'
        }}
      </small>
    </div>
    <p v-if="assessment.self_rating === 1 && assessment.evaluation_passed">
      本次评价通过，但你选择了“完全想不起来”，因此仍安排巩固。
    </p>
  </div>
</template>
