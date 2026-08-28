<script setup lang="ts">
/** 全局 AI 助手：提供不写入业务数据的即时专业问答。 */

import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { apiAskAi } from '@/api/ai'

interface ChatMessage {
  role: 'assistant' | 'user'
  content: string
  sources?: string[]
}

const open = ref(false)
const input = ref('')
const sending = ref(false)
const messageList = ref<HTMLElement>()
const messages = ref<ChatMessage[]>([
  { role: 'assistant', content: '你好，我是 Retrue AI 助手。你可以询问动作、训练部位或康复记录相关问题。我的回答仅供辅助，不替代专业诊断。' },
])

function scrollToBottom(): void {
  nextTick(() => {
    if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
  })
}

async function send(): Promise<void> {
  const question = input.value.trim()
  if (!question || sending.value) return
  messages.value.push({ role: 'user', content: question })
  input.value = ''
  sending.value = true
  scrollToBottom()
  try {
    const result = await apiAskAi(question)
    messages.value.push({
      role: 'assistant',
      content: result.answer,
      sources: result.sources.map((item) => item.name),
    })
  } catch {
    ElMessage.error('AI 助手暂时无法回答，请稍后重试')
  } finally {
    sending.value = false
    scrollToBottom()
  }
}
</script>

<template>
  <div class="assistant-root">
    <transition name="assistant-pop">
      <section v-if="open" class="assistant-panel" aria-label="AI 助手对话">
        <header class="assistant-header">
          <div><strong>AI 助手</strong><span>专业问答 · 仅供辅助</span></div>
          <el-button text aria-label="关闭 AI 助手" @click="open = false"><el-icon><Close /></el-icon></el-button>
        </header>
        <main ref="messageList" class="message-list">
          <div v-for="(message, index) in messages" :key="index" class="message-row" :class="message.role">
            <div class="message-bubble">{{ message.content }}</div>
            <small v-if="message.sources?.length">参考动作：{{ message.sources.join('、') }}</small>
          </div>
          <div v-if="sending" class="message-row assistant"><div class="message-bubble">正在思考…</div></div>
        </main>
        <footer class="assistant-input">
          <el-input v-model="input" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="例如：臀桥怎么做？" @keydown.enter.exact.prevent="send" />
          <div><span>Enter 发送，Shift + Enter 换行</span><el-button type="primary" :loading="sending" :disabled="!input.trim()" @click="send">发送</el-button></div>
        </footer>
      </section>
    </transition>
    <el-button class="assistant-fab" type="primary" circle size="large" aria-label="打开 AI 助手" @click="open = !open">
      <el-icon :size="22"><ChatDotRound /></el-icon>
    </el-button>
  </div>
</template>

<style scoped>
.assistant-root { position: fixed; right: 30px; bottom: 28px; z-index: 2000; }.assistant-fab { width: 52px; height: 52px; box-shadow: 0 8px 24px rgba(7, 163, 88, .35); }.assistant-panel { position: absolute; right: 0; bottom: 66px; display: flex; flex-direction: column; width: 360px; height: 480px; overflow: hidden; border: 1px solid var(--retrue-border); border-radius: var(--retrue-radius-lg); background: var(--retrue-surface); box-shadow: 0 14px 42px rgba(20, 45, 35, .18); }.assistant-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--retrue-border); }.assistant-header div { display: flex; flex-direction: column; gap: 2px; }.assistant-header span, .assistant-input span { color: var(--retrue-text-muted); font-size: 12px; }.message-list { display: flex; flex: 1; flex-direction: column; gap: 12px; padding: 14px; overflow-y: auto; background: var(--retrue-bg); }.message-row { display: flex; flex-direction: column; max-width: 86%; gap: 4px; }.message-row.user { align-self: flex-end; }.message-bubble { padding: 9px 11px; border-radius: 10px; background: var(--retrue-surface); color: var(--retrue-text); font-size: 13px; line-height: 1.55; white-space: pre-wrap; }.message-row.user .message-bubble { background: var(--retrue-primary); color: #fff; }.message-row small { color: var(--retrue-text-muted); font-size: 11px; }.assistant-input { padding: 12px; border-top: 1px solid var(--retrue-border); }.assistant-input > div { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }.assistant-pop-enter-active, .assistant-pop-leave-active { transition: opacity .18s, transform .18s; }.assistant-pop-enter-from, .assistant-pop-leave-to { opacity: 0; transform: translateY(8px); } @media (max-width: 768px) { .assistant-root { display: none; } }
</style>
