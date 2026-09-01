<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { chatHistory, chatSessionId, chatStream, type ChatMessage } from '../api'
import { toast } from '../toast'
import MascotGif from './MascotGif.vue'

interface Seg {
  kind: 'text' | 'code'
  text: string
}

const messages = ref<ChatMessage[]>([])
const input = ref('')
const busy = ref(false)
const restored = ref(false)
const historyFailed = ref(false)
const scrollBox = ref<HTMLElement | null>(null)
const inputBox = ref<HTMLTextAreaElement | null>(null)
const draft = ref<ChatMessage | null>(null)
const controller = ref<AbortController | null>(null)

const SUGGESTIONS = [
  '给我总结一下服务器现在的运行状况',
  '检查内存和磁盘的使用率',
  '有哪些服务状态异常？',
  '最近有没有未解决的工单？',
]

const canSend = computed(() => input.value.trim().length > 0 && !busy.value)

function segments(content: string): Seg[] {
  const out: Seg[] = []
  const re = /```(\w*)\n?([\s\S]*?)```/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(content))) {
    if (m.index > last) out.push({ kind: 'text', text: content.slice(last, m.index) })
    out.push({ kind: 'code', text: m[2] })
    last = m.index + m[0].length
  }
  if (last < content.length) out.push({ kind: 'text', text: content.slice(last) })
  if (!out.length) out.push({ kind: 'text', text: content })
  return out
}

function scrollBottom(smooth = false): void {
  void nextTick(() => {
    const el = scrollBox.value
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  })
}

function grow(el: EventTarget | null): void {
  const ta = el as HTMLTextAreaElement
  ta.style.height = 'auto'
  ta.style.height = `${Math.min(ta.scrollHeight, 140)}px`
}

function stop(): void {
  controller.value?.abort()
}

async function send(text?: string): Promise<void> {
  const content = (text ?? input.value).trim()
  if (!content || busy.value) return
  input.value = ''
  const next: ChatMessage[] = [...messages.value, { role: 'user', content }]
  messages.value = next
  busy.value = true
  draft.value = { role: 'assistant', content: '' }
  controller.value = new AbortController()
  scrollBottom(true)

  try {
    await chatStream(
      next,
      {
        onDelta: (t) => {
          if (draft.value) draft.value = { role: 'assistant', content: draft.value.content + t }
          scrollBottom(false)
        },
        onDone: () => {
          if (draft.value?.content) messages.value.push(draft.value)
          draft.value = null
        },
        onError: (msg) => {
          toast(`对话失败：${msg}`, 'err')
          draft.value = null
        },
      },
      controller.value.signal,
    )
  } finally {
    busy.value = false
    controller.value = null
    if (inputBox.value) {
      inputBox.value.style.height = 'auto'
      inputBox.value.focus()
    }
  }
}

async function loadHistory(): Promise<void> {
  try {
    const payload = await chatHistory()
    messages.value = payload.messages ?? []
    restored.value = true
    scrollBottom()
  } catch {
    historyFailed.value = true
    toast('历史记录暂不可用（后端未实现 /api/chat/messages），可直接开始对话', 'info')
  }
}

onMounted(() => {
  void loadHistory()
})
</script>

<template>
  <div class="chat">
    <div class="chat-head rise">
      <h1 class="head-title">AI 值班对话 <span class="sparkle">✦</span></h1>
      <p class="head-sub num">
        <template v-if="historyFailed">历史通道未连通 · 本会话从零开始</template>
        <template v-else-if="restored">会话已恢复 · 刷新不丢 · 落库于 chat_messages</template>
        <template v-else>正在恢复会话…</template>
      </p>
    </div>

    <div class="chat-card rise" style="animation-delay: 0.05s">
      <div ref="scrollBox" class="chat-scroll">
        <div v-if="!messages.length && !draft" class="empty">
          <div class="empty-mascot"><MascotGif /></div>
          <p class="empty-main">想让我看看服务器什么？</p>
          <p class="empty-sub num">我会自己调监控工具、读真实数据再回答 · 只读查询，不动系统</p>
          <div class="suggests">
            <button
              v-for="s in SUGGESTIONS"
              :key="s"
              class="chip"
              :disabled="busy"
              @click="send(s)"
            >
              {{ s }}
            </button>
          </div>
        </div>

        <div v-else class="thread">
          <div
            v-for="(m, i) in messages"
            :key="`m${i}`"
            class="msg"
            :class="m.role === 'user' ? 'from-user' : 'from-agent'"
          >
            <div v-if="m.role === 'assistant'" class="avatar"><MascotGif /></div>
            <div class="bubble">
              <template v-for="(sg, j) in segments(m.content)" :key="j">
                <pre v-if="sg.kind === 'code'" class="code num">{{ sg.text }}</pre>
                <p v-else class="text">{{ sg.text }}</p>
              </template>
            </div>
          </div>

          <div v-if="draft" class="msg from-agent">
            <div class="avatar"><MascotGif /></div>
            <div class="bubble">
              <p v-if="!draft.content" class="typing">
                <span class="dot-typing"></span><span class="dot-typing"></span><span class="dot-typing"></span>
              </p>
              <template v-else>
                <template v-for="(sg, j) in segments(draft.content)" :key="j">
                  <pre v-if="sg.kind === 'code'" class="code num">{{ sg.text }}</pre>
                  <p v-else class="text">{{ sg.text }}<span class="caret"></span></p>
                </template>
              </template>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input">
        <textarea
          ref="inputBox"
          v-model="input"
          class="input num"
          rows="1"
          placeholder="问点什么…（Enter 发送，Shift+Enter 换行）"
          :disabled="busy"
          @keydown.enter.exact.prevent="send()"
          @input="grow($event.target)"
        ></textarea>
        <button v-if="busy" class="btn stop" @click="stop">■ 停止</button>
        <button v-else class="btn ok send" :disabled="!canSend" @click="send()">发送</button>
      </div>
    </div>

    <p class="chat-foot num">
      会话 <span class="sid">{{ chatSessionId() }}</span> · 与 CLI 同一条 run_agent · 记忆 + 压缩已接入
    </p>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: calc(100vh - 240px);
  min-height: 480px;
}

.chat-head {
  display: flex;
  align-items: baseline;
  gap: 14px;
}

.head-title {
  font-size: 24px;
  font-weight: 700;
}

.sparkle {
  color: var(--teal);
  font-weight: 400;
}

.head-sub {
  font-size: 12px;
  color: var(--ink-faint);
}

.chat-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(58, 68, 66, 0.03), 0 8px 24px rgba(105, 161, 150, 0.07);
}

.chat-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 24px 26px;
  background:
    radial-gradient(420px 200px at 8% 0%, rgba(105, 161, 150, 0.05), transparent 70%),
    var(--panel-2);
}

.empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  padding: 24px;
}

.empty-mascot {
  width: 76px;
  height: 76px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid var(--line-strong);
  background: #fff;
  box-shadow: 0 4px 14px rgba(105, 161, 150, 0.18);
}

.empty-main {
  font-size: 16px;
  font-weight: 700;
  color: var(--ink);
  margin-top: 4px;
}

.empty-sub {
  font-size: 12px;
  color: var(--ink-faint);
}

.suggests {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 12px;
  max-width: 560px;
}

.chip {
  font-size: 12px;
  font-weight: 700;
  color: var(--teal-deep);
  background: #fff;
  border: 1.5px solid var(--line-strong);
  border-radius: 999px;
  padding: 7px 15px;
  cursor: pointer;
  box-shadow: 0 2px 0 var(--line-strong);
  transition: all 0.15s ease;
}
.chip:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 3px 0 var(--line-strong);
  color: var(--pink-deep);
  border-color: var(--teal);
  background: var(--teal-soft);
}
.chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.thread {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  animation: rise 0.35s cubic-bezier(0.2, 0.9, 0.3, 1.1) both;
}

.msg.from-user {
  justify-content: flex-end;
}

.avatar {
  width: 34px;
  height: 34px;
  flex: none;
  border-radius: 50%;
  overflow: hidden;
  border: 1.5px solid var(--line-strong);
  background: #fff;
}

.bubble {
  max-width: 76%;
  padding: 11px 16px;
  border-radius: 18px;
  font-size: 13.5px;
  line-height: 1.7;
  word-break: break-word;
  white-space: pre-wrap;
}

.from-user .bubble {
  background: linear-gradient(135deg, var(--teal), var(--teal-deep));
  color: #fff;
  border-bottom-right-radius: 6px;
  box-shadow: 0 4px 12px rgba(87, 138, 128, 0.22);
}

.from-agent .bubble {
  background: var(--panel);
  border: 1px solid var(--line);
  border-bottom-left-radius: 6px;
  color: var(--ink);
  box-shadow: 0 3px 10px rgba(58, 68, 66, 0.05);
}

.bubble .text {
  white-space: pre-wrap;
}

.bubble .code {
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.6;
  background: var(--panel-3);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
  margin: 6px 0;
  overflow-x: auto;
  white-space: pre;
}

.caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -2px;
  background: var(--teal-deep);
  animation: blink 0.9s steps(2) infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.typing {
  display: flex;
  gap: 5px;
  align-items: center;
  height: 20px;
}

.dot-typing {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--teal);
  animation: typing-bob 1s ease-in-out infinite;
}
.dot-typing:nth-child(2) { animation-delay: 0.15s; }
.dot-typing:nth-child(3) { animation-delay: 0.3s; }

@keyframes typing-bob {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-5px); opacity: 1; }
}

.chat-input {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 14px 16px;
  border-top: 1px solid var(--line);
  background: var(--panel);
}

.input {
  flex: 1;
  resize: none;
  font-family: var(--round);
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--ink);
  background: var(--panel-2);
  border: 1.5px solid var(--line-strong);
  border-radius: 14px;
  padding: 10px 14px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.input:focus {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px rgba(105, 161, 150, 0.14);
}
.input:disabled {
  opacity: 0.7;
}

.send {
  flex: none;
}

.stop {
  flex: none;
  color: #e11d48;
  border-color: #fecdd3;
  background: #fff1f2;
  box-shadow: 0 3px 0 #fecdd3;
}

.chat-foot {
  font-size: 11px;
  color: var(--ink-faint);
  text-align: right;
  letter-spacing: 0.04em;
}

.sid {
  font-family: var(--mono);
  color: var(--teal-deep);
}
</style>