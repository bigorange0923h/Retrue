/** 仅供本地视觉验收：提供虚构用户与 SSE 样例，不连接业务后端或数据库。
 * 先 npm run build，再 node tests/preview-assistant.mjs；打开 /assistant 或 /mobile。
 * 输入“断线”可验证流中断提示。关闭进程即丢弃全部样例状态。
 */
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve, sep, extname } from 'node:path'

const root = fileURLToPath(new URL('../dist/', import.meta.url))
const contentTypes = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml' }
let nextConversation = 0
const server = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://127.0.0.1').pathname
  const json = (data) => { response.writeHead(200, { 'Content-Type': 'application/json' }); response.end(JSON.stringify({ code: 200, message: '测试样例', data })) }
  if (path === '/api/auth/me/') return json({ id: 1, username: 'preview', display_name: '测试康复师', is_active: true, is_superuser: false })
  if (path === '/api/assistant/turns/stream/') {
    let body = ''
    for await (const chunk of request) body += chunk
    const input = JSON.parse(body)
    response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' })
    response.write(': connected\n\n')
    let sequence = 0
    const send = (event, data) => response.write(`id: ${++sequence}\nevent: ${event}\ndata: ${JSON.stringify({ code: 200, message: '测试样例', data })}\n\n`)
    send('progress', { stage: 'understand', label: '正在识别需求', status: 'running' })
    const timers = [
      setTimeout(() => {
        if (input.message.includes('断线')) { response.destroy(); return }
        send('progress', { stage: 'understand', label: '正在识别需求', status: 'completed' })
        send('progress', { stage: 'compose_reply', label: '正在整理回复', status: 'running' })
      }, 4000),
      setTimeout(() => {
        send('progress', { stage: 'compose_reply', label: '正在整理回复', status: 'completed' })
        send('result', { task_id: 1, status: 'completed', intent: 'general_knowledge', reply_content: '这是视觉验收样例：步骤更新后，最终回复正常显示。', cards: [] })
        response.end()
      }, 16000),
    ]
    response.on('close', () => timers.forEach(clearTimeout))
    return
  }
  if (path === '/api/conversations/' && request.method === 'POST') return json({ id: ++nextConversation, customer: null })
  if (/^\/api\/conversations\/\d+\/$/.test(path)) return json({ id: nextConversation, customer: null, messages: [] })
  if (path.startsWith('/api/')) return json([])
  if (path === '/mobile') {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
    return response.end('<title>390px 手机视觉验收</title><style>body{margin:0}iframe{width:390px;height:844px;border:0}</style><iframe src="/assistant" title="手机对话页"></iframe>')
  }
  const target = path.startsWith('/assets/') ? resolve(root, `.${path}`) : resolve(root, 'index.html')
  if (!target.startsWith(resolve(root) + sep)) { response.writeHead(403); return response.end() }
  try {
    const body = await readFile(target)
    response.writeHead(200, { 'Content-Type': contentTypes[extname(target)] || 'application/octet-stream' })
    response.end(body)
  } catch { response.writeHead(404); response.end() }
})
server.listen(5187, '127.0.0.1', () => console.log('仅测试样例：http://127.0.0.1:5187/assistant；手机：/mobile'))
