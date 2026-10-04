import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { homeTrainingText, formatHomeExercise } from './homeTraining.ts'

test('客户文案完整保留剂量、频率、注意事项且不含内部编号', () => {
  const text = homeTrainingText({ id: 987, customer: 654, customer_name: '演示客户', title: '家庭练习', frequency: '每日', note: '疼痛加重时停止并联系康复师', created_at: '', updated_at: '', exercises: [
    { exercise_name: '靠墙静蹲', sets: 3, reps: 2, duration_seconds: 30, frequency: '早晚', note: '保持平稳呼吸', sort_order: 0 },
  ] })
  for (const value of ['3 组', '每组 2 次', '每次 30 秒', '早晚', '保持平稳呼吸', '整体频率：每日', '疼痛加重']) assert.ok(text.includes(value))
  assert.ok(!text.includes('987') && !text.includes('654'))
})
test('未填写剂量明确显示缺失，不编造次数', () => {
  assert.equal(formatHomeExercise({ exercise_name: '臀桥', sets: null, reps: null, duration_seconds: null, frequency: '', note: '', sort_order: 0 }), '臀桥：训练量未填写')
})
