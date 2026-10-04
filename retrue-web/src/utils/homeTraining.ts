import type { HomeTrainingExercise, HomeTrainingPlan } from '../types/api'

/** 客户版训练量保留组、次、时长和单动作频率；空值不猜测默认剂量。 */
export function formatHomeExercise(exercise: HomeTrainingExercise): string {
  const dose = [
    exercise.sets == null ? '' : `${exercise.sets} 组`,
    exercise.reps == null ? '' : `每组 ${exercise.reps} 次`,
    exercise.duration_seconds == null ? '' : `每次 ${exercise.duration_seconds} 秒`,
    exercise.frequency,
  ].filter(Boolean).join('，')
  return `${exercise.exercise_name}${dose ? `：${dose}` : '：训练量未填写'}${exercise.note ? `；注意：${exercise.note}` : ''}`
}

/** 生成可核对、可复制的完整客户文案，不包含内部资源编号。 */
export function homeTrainingText(plan: HomeTrainingPlan): string {
  return [
    plan.title,
    plan.customer_name ? `客户：${plan.customer_name}` : '',
    plan.frequency ? `整体频率：${plan.frequency}` : '',
    ...[...plan.exercises].sort((a, b) => a.sort_order - b.sort_order).map((item, index) => `${index + 1}. ${formatHomeExercise(item)}`),
    plan.note ? `整体注意事项：${plan.note}` : '',
  ].filter(Boolean).join('\n')
}
