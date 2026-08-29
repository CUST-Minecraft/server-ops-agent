<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api, type ApprovalRequest } from '../api'
import { fmtCountdown } from '../format'
import { toast } from '../toast'

const reqs = ref<ApprovalRequest[]>([])
const loading = ref(true)
const error = ref('')
const busy = ref<Record<number, 'approve' | 'reject'>>({})
const now = ref(new Date())
let timer: number | undefined
let ticker: number | undefined

async function load(): Promise<void> {
  try {
    error.value = ''
    const payload = await api.approvals()
    reqs.value = payload.reqs
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    toast(`审批单获取失败：${error.value}`, 'err')
  } finally {
    loading.value = false
  }
}

async function act(id: number, kind: 'approve' | 'reject'): Promise<void> {
  if (busy.value[id]) return
  busy.value = { ...busy.value, [id]: kind }
  try {
    const result = kind === 'approve' ? await api.approve(id) : await api.reject(id)
    toast(result.message, result.ok ? 'ok' : 'info')
    await load()
  } catch (e) {
    toast(`操作失败：${e instanceof Error ? e.message : String(e)}`, 'err')
  } finally {
    const next = { ...busy.value }
    delete next[id]
    busy.value = next
  }
}

onMounted(() => {
  void load()
  timer = window.setInterval(() => void load(), 15000)
  ticker = window.setInterval(() => {
    now.value = new Date()
  }, 1000)
})
onUnmounted(() => {
  window.clearInterval(timer)
  window.clearInterval(ticker)
})
</script>

<template>
  <div class="approvals">
    <div class="head rise">
      <h1 class="head-title">待审批</h1>
      <p class="head-sub num">{{ reqs.length }} 张挂起 · 批了即执行，务必核对命令</p>
    </div>

    <div v-if="loading && !reqs.length" class="panel rise" style="animation-delay: 0.05s">
      <div v-for="i in 2" :key="i" class="skeleton" style="height: 130px; margin-bottom: 14px"></div>
    </div>

    <div v-else-if="error && !reqs.length" class="panel err-panel rise" style="animation-delay: 0.05s">
      <p class="err-title num">✕ 审批单获取失败</p>
      <p class="err-body num">{{ error }}</p>
    </div>

    <div v-else-if="!reqs.length" class="panel empty-panel rise" style="animation-delay: 0.05s">
      <span class="dot on"></span>
      <p class="empty-main">没有待审批的操作</p>
      <p class="empty-sub num">所有闸门已放行或处理完毕，系统自治运行中</p>
    </div>

    <TransitionGroup v-else name="req" tag="div" class="req-list">
      <div v-for="(r, idx) in reqs" :key="r.id" class="panel req-card rise" :style="{ animationDelay: `${0.04 + idx * 0.05}s` }">
        <div class="req-head">
          <span class="req-id num">#{{ r.id }}</span>
          <span class="req-tool num">{{ r.tool }}</span>
          <span class="req-exp num" :class="{ expired: fmtCountdown(r.expires_at, now).startsWith('已过期') }">
            {{ fmtCountdown(r.expires_at, now) }}
          </span>
        </div>

        <pre class="req-args num">{{ JSON.stringify(r.args, null, 2) }}</pre>

        <p class="req-reason">
          <span class="req-reason-label">理由</span>
          {{ r.reason }}
        </p>

        <div class="req-actions">
          <button
            class="btn ok"
            :disabled="!!busy[r.id]"
            :class="{ busy: busy[r.id] === 'approve' }"
            @click="act(r.id, 'approve')"
          >
            {{ busy[r.id] === 'approve' ? '执行中…' : '批准' }}
          </button>
          <button
            class="btn no"
            :disabled="!!busy[r.id]"
            :class="{ busy: busy[r.id] === 'reject' }"
            @click="act(r.id, 'reject')"
          >
            {{ busy[r.id] === 'reject' ? '处理中…' : '驳回' }}
          </button>
        </div>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.approvals {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.head {
  display: flex;
  align-items: baseline;
  gap: 14px;
}

.head-title {
  font-size: 24px;
  font-weight: 700;
}

.head-sub {
  font-size: 12px;
  color: var(--ink-faint);
}

.req-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.req-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.req-id {
  font-size: 13px;
  font-weight: 500;
  color: var(--teal);
}

.req-tool {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0.02em;
}

.req-exp {
  margin-left: auto;
  font-size: 11px;
  color: var(--green);
}

.req-exp.expired {
  color: var(--red);
}

.req-args {
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-dim);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.req-reason {
  font-size: 13px;
  color: var(--ink-dim);
  line-height: 1.6;
  margin-bottom: 14px;
}

.req-reason-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--ink-faint);
  margin-right: 8px;
  border: 1px solid var(--line);
  padding: 1px 7px;
  border-radius: 6px;
}

.req-actions {
  display: flex;
  gap: 10px;
}

.empty-panel {
  text-align: center;
  padding: 56px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.empty-main {
  font-size: 15px;
  font-weight: 500;
  color: var(--ink-dim);
}

.empty-sub {
  font-size: 12px;
  color: var(--ink-faint);
}

.err-title {
  color: var(--red);
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.err-body {
  font-size: 12px;
  color: var(--ink-dim);
}

.req-enter-active,
.req-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.req-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.req-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
.req-move {
  transition: transform 0.22s ease;
}
</style>