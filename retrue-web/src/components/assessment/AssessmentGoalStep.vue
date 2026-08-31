<script setup lang="ts">
/** 第四步：确认康复目标和康复师补充观察。 */

import type { AssessmentForm } from '@/api/assessments'

const props = defineProps<{ reassessment: boolean }>()
const form = defineModel<AssessmentForm>({ required: true })
</script>

<template>
  <section class="assessment-step">
    <div class="step-intro">
      <p class="eyebrow">第四步 / 目标与备注</p>
      <h3>把“想恢复什么”写成可回看的目标</h3>
      <p>优先记录客户希望恢复的活动，例如“可以无痛上下楼”或“恢复每周三次跑步”。</p>
    </div>

    <el-form label-position="top" class="goal-form">
      <el-form-item label="康复目标" required>
        <el-input v-model="form.rehab_goal" type="textarea" :rows="4" placeholder="希望恢复什么活动？有什么时间或场景目标？" maxlength="1500" show-word-limit />
      </el-form-item>

      <el-form-item v-if="props.reassessment" label="本次与上次相比的当前状态">
        <el-input v-model="form.current_status" type="textarea" :rows="3" placeholder="例如：走路疼痛减轻，但下楼仍有不适" maxlength="1200" show-word-limit />
      </el-form-item>

      <el-form-item label="康复师观察与补充备注">
        <el-input v-model="form.note" type="textarea" :rows="4" placeholder="记录需要留意的情况、沟通重点或后续建议" maxlength="2000" show-word-limit />
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

.goal-form {
  width: 100%;
}
</style>
