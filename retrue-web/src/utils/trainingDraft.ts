/** 确认时按项目类型清理互斥数量，避免隐藏表单值写入正式记录。 */
import type { TrainingExercise } from '@/types/api'

export function toConfirmedExercise(exercise: TrainingExercise, index: number): TrainingExercise {
  const activityType = exercise.activity_type || 'exercise'
  if (activityType === 'exercise') {
    return { ...exercise, activity_type: activityType, quantity: null, unit: '', sort_order: index }
  }
  return { ...exercise, activity_type: activityType, sets: null, reps: null, sort_order: index }
}
