<script setup lang="ts">
/** 第一步：记录本次问题与症状开始情况。 */

import type { AssessmentForm } from '@/api/assessments'

const props = defineProps<{
  lockedAssessmentType: boolean
  customerName?: string
}>()

const form = defineModel<AssessmentForm>({ required: true })

const onsetModes = [
  { label: '受伤', value: 'injury' },
  { label: '突然发作', value: 'sudden' },
  { label: '逐渐加重', value: 'gradual' },
  { label: '术后', value: 'postoperative' },
  { label: '其他', value: 'other' },
  { label: '暂不清楚', value: 'unknown' },
]
</script>

<template>
  <section class="assessment-step">
    <div class="step-intro">
      <p class="eyebrow">第一步 / 本次问题</p>
      <h3>先记录这次最需要解决的问题</h3>
      <p>按客户本次就诊的主要困扰填写，暂时不清楚的内容可以选择“暂不清楚”。</p>
    </div>

    <el-alert v-if="props.customerName" :title="`当前客户：${props.customerName}`" type="info" :closable="false" show-icon />

    <el-form label-position="top" class="step-form">
      <el-form-item label="评估日期" required>
        <el-date-picker v-model="form.assessment_date" type="date" value-format="YYYY-MM-DD" class="full-width" placeholder="选择本次评估日期" />
      </el-form-item>

      <el-form-item label="评估类型" required>
        <el-select v-if="!props.lockedAssessmentType" v-model="form.assessment_type" class="full-width">
          <el-option label="首次评估" value="initial" />
          <el-option label="阶段复评" value="reassessment" />
        </el-select>
        <div v-else class="locked-type">
          <el-tag type="primary">{{ form.assessment_type === 'initial' ? '首次评估' : '阶段复评' }}</el-tag>
          <span>评估类型创建后不可更改</span>
        </div>
      </el-form-item>

      <el-form-item label="现在最困扰的问题或不适部位" required>
        <el-input
          v-model="form.chief_complaint"
          type="textarea"
          :rows="3"
          placeholder="例如：右膝下楼时前侧疼痛，蹲起困难"
          maxlength="1000"
          show-word-limit
        />
      </el-form-item>

      <div class="form-grid">
        <el-form-item label="症状开始日期">
          <el-date-picker v-model="form.onset_date" type="date" value-format="YYYY-MM-DD" class="full-width" placeholder="知道具体日期时填写" />
        </el-form-item>
        <el-form-item label="开始时间补充说明">
          <el-input v-model="form.onset_description" placeholder="例如：大约两周前、去年冬天" />
        </el-form-item>
      </div>

      <el-form-item label="大致是怎样开始的">
        <el-radio-group v-model="form.onset_mode" class="choice-grid">
          <el-radio v-for="mode in onsetModes" :key="mode.value" :value="mode.value">{{ mode.label }}</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
  </section>
</template>

<style scoped>
.assessment-step {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.step-intro h3 {
  margin: 4px 0 7px;
  font-size: 20px;
}

.step-intro p {
  margin: 0;
  color: var(--retrue-text-secondary);
  line-height: 1.7;
}

.step-intro .eyebrow {
  color: var(--retrue-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.step-form {
  width: 100%;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.full-width {
  width: 100%;
}

.locked-type {
  display: flex;
  min-height: 32px;
  align-items: center;
  gap: 10px;
  color: var(--retrue-text-secondary);
  font-size: 13px;
}

.choice-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
}

.choice-grid :deep(.el-radio) {
  min-height: 44px;
  margin-right: 0;
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
</style>
