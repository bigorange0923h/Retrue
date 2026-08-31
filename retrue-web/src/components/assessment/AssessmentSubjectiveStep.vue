<script setup lang="ts">
/** 第二步：以问题式文案记录客户主观感受和生活影响。 */

import type { AssessmentForm } from '@/api/assessments'

const form = defineModel<AssessmentForm>({ required: true })

const fields = [
  { key: 'aggravating_factors', label: '哪些动作或场景会加重？', placeholder: '例如：上下楼、久坐后站起、训练后' },
  { key: 'relieving_factors', label: '哪些方式可以缓解？', placeholder: '例如：休息、热敷、改变姿势' },
  { key: 'prior_care', label: '之前是否就医或接受过治疗？', placeholder: '没有、做过什么检查或治疗，都可以记录' },
  { key: 'medical_history', label: '既往伤病、手术和用药情况', placeholder: '不清楚时可填写“暂不清楚”' },
  { key: 'surgery_history', label: '手术史补充', placeholder: '没有手术可填写“无”' },
  { key: 'medication', label: '当前用药情况', placeholder: '药物名称、频率；不清楚可填写“暂不清楚”' },
  { key: 'exercise_habits', label: '日常运动习惯', placeholder: '运动项目、频率和近期训练量' },
  { key: 'work_demands', label: '工作负荷', placeholder: '久坐、久站、搬运或重复动作等' },
  { key: 'sleep_impact', label: '对睡眠的影响', placeholder: '不影响、入睡困难、夜间痛醒等' },
] as const
</script>

<template>
  <section class="assessment-step">
    <div class="step-intro">
      <p class="eyebrow">第二步 / 主观情况</p>
      <h3>用客户的话，记录症状如何影响生活</h3>
      <p>这些信息帮助后续复评时判断变化，也可以先填写“暂不清楚”。</p>
    </div>

    <el-form label-position="top" class="subjective-form">
      <el-form-item label="现在最困扰的问题是什么？" required>
        <el-input v-model="form.chief_complaint" type="textarea" :rows="3" placeholder="保留客户原话或用一句话概括" maxlength="1000" show-word-limit />
      </el-form-item>

      <div class="subjective-grid">
        <el-form-item v-for="field in fields" :key="field.key" :label="field.label">
          <el-input v-model="form[field.key]" type="textarea" :rows="2" :placeholder="field.placeholder" maxlength="1000" show-word-limit />
        </el-form-item>
      </div>
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

.subjective-form,
.subjective-grid {
  width: 100%;
}

.subjective-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

@media (max-width: 768px) {
  .subjective-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
