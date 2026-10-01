<script setup lang="ts">
/** 第二步：以问题式文案记录客户主观感受和生活影响。 */

import type { AssessmentForm } from '@/api/assessments'
import { ref } from 'vue'

const form = defineModel<AssessmentForm>({ required: true })
const emit = defineEmits<{ 'edit-problem': [] }>()
const expanded = ref<string[]>([])

const fields = [
  { key: 'aggravating_factors', label: '哪些动作或场景会加重？', placeholder: '例如：上下楼、久坐后站起、训练后' },
  { key: 'relieving_factors', label: '哪些方式可以缓解？', placeholder: '例如：休息、热敷、改变姿势' },
  { key: 'prior_care', label: '之前是否就医或接受过治疗？', placeholder: '没有、做过什么检查或治疗，都可以记录' },
  { key: 'medical_history', label: '既往伤病情况', placeholder: '记录相关伤病；手术和用药在下方单独补充' },
  { key: 'surgery_history', label: '手术史', placeholder: '已确认没有手术时填写“无”；未询问时留空' },
  { key: 'medication', label: '当前用药情况', placeholder: '药物名称、频率；不清楚可填写“暂不清楚”' },
  { key: 'exercise_habits', label: '日常运动习惯', placeholder: '运动项目、频率和近期训练量' },
  { key: 'work_demands', label: '工作负荷', placeholder: '久坐、久站、搬运或重复动作等' },
  { key: 'sleep_impact', label: '对睡眠的影响', placeholder: '不影响、入睡困难、夜间痛醒等' },
] as const

const groups = [
  { title: '症状与就医情况', fields: fields.slice(0, 3) },
  { title: '既往伤病', fields: fields.slice(3, 4) },
  { title: '运动与工作', fields: fields.slice(6, 8) },
]
</script>

<template>
  <section class="assessment-step">
    <div class="step-intro">
      <p class="eyebrow">第二步 / 主观情况</p>
      <h3>用客户的话，记录症状如何影响生活</h3>
      <p>主诉已带入，只需补充相关情况。未询问的内容可留空，不会自动记为“无”。</p>
    </div>

    <el-form label-position="top" class="subjective-form">
      <div class="problem-summary">
        <div><span>本次主要问题</span><p>{{ form.chief_complaint || '尚未记录' }}</p></div>
        <el-button text type="primary" @click="emit('edit-problem')">修改</el-button>
      </div>

      <section v-for="group in groups" :key="group.title" class="field-group">
        <h4>{{ group.title }}</h4>
        <div class="subjective-grid">
          <el-form-item v-for="field in group.fields" :key="field.key" :label="field.label">
            <el-input v-model="form[field.key]" type="textarea" :rows="2" :placeholder="field.placeholder" maxlength="1000" show-word-limit />
          </el-form-item>
        </div>
      </section>
      <el-collapse v-model="expanded">
        <el-collapse-item name="history">
          <template #title>手术与用药 <span class="group-status">{{ form.surgery_history || form.medication ? '已有记录，可展开核对' : '尚未记录，可展开补充' }}</span></template>
          <div class="subjective-grid">
            <el-form-item v-for="field in fields.slice(4, 6)" :key="field.key" :label="field.label">
              <el-input v-model="form[field.key]" type="textarea" :rows="2" :placeholder="field.placeholder" maxlength="1000" show-word-limit />
            </el-form-item>
          </div>
        </el-collapse-item>
        <el-collapse-item name="sleep">
          <template #title>睡眠影响 <span class="group-status">{{ form.sleep_impact ? '已有记录，可展开核对' : '尚未记录，可展开补充' }}</span></template>
          <el-form-item :label="fields[8]!.label">
            <el-input v-model="form.sleep_impact" type="textarea" :rows="2" :placeholder="fields[8]!.placeholder" maxlength="1000" show-word-limit />
          </el-form-item>
        </el-collapse-item>
      </el-collapse>
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

.problem-summary { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 14px 16px; margin-bottom: 22px; border-radius: var(--retrue-radius-sm); background: var(--retrue-bg); }
.problem-summary > div { min-width: 0; }
.problem-summary span, .group-status { color: var(--retrue-text-secondary); font-size: 12px; }
.problem-summary p { margin: 6px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.field-group h4 { margin: 8px 0 16px; font-size: 15px; }
.group-status { margin-left: 12px; }

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
