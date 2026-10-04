import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { createCustomerScope } from './customerScope.ts'

test('A 请求晚于 B 返回时不能回填 B 页面', async () => {
  const scope = createCustomerScope()
  scope.reset(1)
  const a = scope.capture()
  scope.reset(2)
  const b = scope.capture()
  let page = ''
  await Promise.resolve().then(() => { if (scope.isCurrent(b)) page = 'B' })
  await Promise.resolve().then(() => { if (scope.isCurrent(a)) page = 'A' })
  assert.equal(page, 'B')
})
test('切回同一客户后仍拒绝上一轮的响应', () => {
  const scope = createCustomerScope()
  scope.reset(1)
  const old = scope.capture()
  scope.reset(2)
  scope.reset(1)
  assert.equal(scope.isCurrent(old), false)
})
test('保存时捕获客户，不被后续全局选择改变', () => {
  const scope = createCustomerScope()
  scope.reset(7)
  const saving = scope.capture()
  scope.reset(8)
  assert.equal(saving.customerId, 7)
  assert.equal(scope.isCurrent(saving), false)
})
