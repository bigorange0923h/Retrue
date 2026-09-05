/** 使用 Node 原生流验证中文拆包、SSE 帧边界与终态关闭。 */
import assert from 'node:assert/strict'
import test from 'node:test'
import { consumeSse } from '../src/api/sse.ts'

const encoder = new TextEncoder()

test('逐字节传输中文及 CRLF，忽略心跳，多行 data 合并', async () => {
  const bytes = encoder.encode(': heartbeat\r\n\r\nevent: progress\r\ndata: 正在\r\ndata: 查询\r\n\r\nevent: result\ndata: 完成\n\n')
  const stream = new ReadableStream({
    start(controller) {
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte))
      controller.close()
    },
  })
  const events = []
  await consumeSse(stream, (event, data) => { events.push([event, data]); return event === 'result' }, () => {})
  assert.deepEqual(events, [['progress', '正在\n查询'], ['result', '完成']])
})

test('同一块含多帧时收到终态即停止，取消剩余流', async () => {
  let cancelled = false
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(encoder.encode('event: result\ndata: 完成\n\nevent: progress\ndata: 不应处理\n\n')) },
    cancel() { cancelled = true },
  })
  const events = []
  await consumeSse(stream, (event) => { events.push(event); return true }, () => {})
  assert.deepEqual(events, ['result'])
  assert.equal(cancelled, true)
})

test('截断帧不能被当成完整结果', async () => {
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(encoder.encode('event: result\ndata: 不完整')); controller.close() },
  })
  let calls = 0
  await consumeSse(stream, () => { calls++; return true }, () => {})
  assert.equal(calls, 0)
})

test('接收处理失败也会关闭流，错误继续向调用方传播', async () => {
  let cancelled = false
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(encoder.encode('event: error\ndata: 失败\n\n')) },
    cancel() { cancelled = true },
  })
  await assert.rejects(consumeSse(stream, () => { throw new Error('处理失败') }, () => {}), /处理失败/)
  assert.equal(cancelled, true)
})
