<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api, type StatusPayload } from '../api'
import { pctColor, relTime } from '../format'
import { toast } from '../toast'
import MascotGif from './MascotGif.vue'

const data = ref<StatusPayload | null>(null)
const loading = ref(true)
const error = ref('')
let timer: number | undefined

async function load(): Promise<void> {
  try {
    error.value = ''
    data.value = await api.status()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    toast(`总览数据获取失败：${error.value}`, 'err')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  timer = window.setInterval(() => void load(), 30000)
})
onUnmounted(() => window.clearInterval(timer))

const services = () => (data.value?.snap ? Object.entries(data.value.snap.services_status) : [])

function svcState(name: string): 'on' | 'off' | 'warn' {
  const s = data.value?.snap?.services_status[name] ?? ''
  const v = s.toLowerCase()
  if (v === 'active' || v === 'running') return 'on'
  if (v === 'inactive' || v === 'failed' || v === 'stopped') return 'off'
  return 'warn'
}
</script>

<template>
  <div class="overview">
    <div class="overview-head rise">
      <h1 class="head-title">值班总览 <span class="sparkle">✦</span></h1>
      <p class="head-sub">
        <span v-if="loading && !data">正在召唤数据…</span>
        <span v-else-if="error">链路异常，详见下方提示</span>
        <span v-else-if="data?.snap">最近快照 {{ relTime(data.snap.collected_at) }}</span>
        <span v-else>暂无快照，运行 <b>serveragent run</b> 开始采集</span>
      </p>
    </div>

    <template v-if="loading && !data">
      <div class="panel loading-panel rise">
        <div class="loading-inner">
          <div class="mascot-box"><MascotGif /></div>
          <p class="loading-text">正在连接御坂网络…</p>
        </div>
      </div>
    </template>

    <template v-else-if="error && !data">
      <div class="panel err-panel rise" style="animation-delay: 0.05s">
        <div class="err-inner">
          <div class="mascot-box"><MascotGif /></div>
          <div class="err-body">
            <p class="err-title">✕ API 链路异常</p>
            <p class="err-detail num">{{ error }}</p>
            <p class="err-hint">
              检查：uvicorn 是否在 8000 端口运行（正式环境）/ vite 代理是否指向后端（开发环境）·
              <a href="#/incidents">先看看工单 →</a>
            </p>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="grid g-metrics">
        <div class="panel metric rise" style="animation-delay: 0.03s">
          <p class="panel-title">CPU</p>
          <p class="metric-val num" :style="{ color: pctColor(data?.snap?.cpu_used_pct ?? 0) }">
            {{ (data?.snap?.cpu_used_pct ?? 0).toFixed(1) }}<span class="pct">%</span>
          </p>
          <div class="bar">
            <div class="bar-fill" :style="{ width: `${data?.snap?.cpu_used_pct ?? 0}%`, background: pctColor(data?.snap?.cpu_used_pct ?? 0) }"></div>
          </div>
          <p class="metric-sub num">
            load {{ (data?.snap?.load_1m ?? 0).toFixed(2) }} / {{ (data?.snap?.load_5m ?? 0).toFixed(2) }} / {{ (data?.snap?.load_15m ?? 0).toFixed(2) }}
          </p>
        </div>

        <div class="panel metric rise" style="animation-delay: 0.08s">
          <p class="panel-title">内存</p>
          <p class="metric-val num" :style="{ color: pctColor(data?.snap?.mem_used_pct ?? 0) }">
            {{ (data?.snap?.mem_used_pct ?? 0).toFixed(1) }}<span class="pct">%</span>
          </p>
          <div class="bar">
            <div class="bar-fill" :style="{ width: `${data?.snap?.mem_used_pct ?? 0}%`, background: pctColor(data?.snap?.mem_used_pct ?? 0) }"></div>
          </div>
          <p class="metric-sub num">可用 {{ (data?.snap?.mem_available_mb ?? 0).toFixed(0) }} MB</p>
        </div>

        <div class="panel metric rise" style="animation-delay: 0.13s">
          <p class="panel-title">磁盘</p>
          <p class="metric-val num" :style="{ color: pctColor(data?.snap?.disk_used_pct ?? 0) }">
            {{ (data?.snap?.disk_used_pct ?? 0).toFixed(1) }}<span class="pct">%</span>
          </p>
          <div class="bar">
            <div class="bar-fill" :style="{ width: `${data?.snap?.disk_used_pct ?? 0}%`, background: pctColor(data?.snap?.disk_used_pct ?? 0) }"></div>
          </div>
          <p class="metric-sub num">快照 #{{ data?.snap?.id ?? '-' }}</p>
        </div>
      </div>

      <div class="grid g-main">
        <div class="panel svc-panel rise" style="animation-delay: 0.18s">
          <p class="panel-title">服务状态</p>
          <div v-if="services().length" class="svc-grid">
            <div v-for="[name, state] in services()" :key="name" class="svc">
              <span class="dot" :class="svcState(name)"></span>
              <span class="svc-name num">{{ name }}</span>
              <span class="svc-state num">{{ state }}</span>
            </div>
          </div>
          <p v-else class="empty-note">等待采集器上报服务状态…</p>
        </div>

        <div class="side">
          <div class="panel latest-panel rise" style="animation-delay: 0.23s">
            <p class="panel-title">最近工单</p>
            <template v-if="data?.latest">
              <div class="latest-row">
                <span class="num latest-id">#{{ data.latest.id }}</span>
                <span class="pill" :class="data.latest.status">{{ data.latest.status }}</span>
              </div>
              <p class="latest-title">{{ data.latest.title }}</p>
              <p class="latest-sub num">
                {{ relTime(data.latest.opened_at) }} 开启 ·
                <a href="#/incidents">全部工单 →</a>
              </p>
            </template>
            <p v-else class="empty-note">暂无工单 ✨</p>
          </div>

          <div class="panel pending-panel rise" style="animation-delay: 0.28s">
            <p class="panel-title">待审批</p>
            <div class="pending-row">
              <span class="pending-num num" :class="{ hot: (data?.pending ?? 0) > 0 }">
                {{ data?.pending ?? 0 }}
              </span>
              <span class="dot" :class="(data?.pending ?? 0) > 0 ? 'warn' : 'on'"></span>
            </div>
            <p class="pending-hint">
              <template v-if="(data?.pending ?? 0) > 0">
                有操作等待值班长签字 ·
                <a href="#/approvals">去审批 →</a>
              </template>
              <template v-else>无挂起操作，系统自治运行中 ✦</template>
            </p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.overview-head {
  display: flex;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 2px;
}

.head-title {
  font-size: 24px;
  font-weight: 900;
  letter-spacing: 0.02em;
}

.sparkle {
  color: var(--pink);
  font-size: 16px;
  animation: twinkle 2.6s ease-in-out infinite;
  display: inline-block;
}

@keyframes twinkle {
  0%, 100% { transform: scale(1) rotate(0deg); }
  50% { transform: scale(1.25) rotate(18deg); }
}

.head-sub {
  font-size: 13px;
  color: var(--ink-dim);
}

.head-sub b {
  color: var(--pink-deep);
  font-weight: 700;
}

.grid {
  display: grid;
  gap: 16px;
}

.g-metrics {
  grid-template-columns: repeat(3, 1fr);
}

.metric-val {
  font-size: 34px;
  font-weight: 700;
  line-height: 1;
  margin: 4px 0 14px;
}

.pct {
  font-size: 14px;
  color: var(--ink-faint);
  margin-left: 2px;
}

.bar {
  height: 8px;
  background: var(--panel-3);
  border-radius: 99px;
  overflow: hidden;
  margin-bottom: 10px;
}

.bar-fill {
  height: 100%;
  border-radius: 99px;
  transition: width 0.6s ease;
}

.metric-sub {
  font-size: 11px;
  color: var(--ink-faint);
}

.g-main {
  grid-template-columns: 7fr 5fr;
}

.svc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.svc {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--panel-2);
  border: 1.5px solid var(--line);
  border-radius: 14px;
  transition: all 0.18s ease;
}

.svc:hover {
  border-color: var(--pink);
  transform: translateY(-1px);
}

.svc-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--ink);
}

.svc-state {
  margin-left: auto;
  font-size: 10px;
  color: var(--ink-faint);
}

.side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.latest-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.latest-id {
  font-size: 13px;
  font-weight: 700;
  color: var(--pink-deep);
}

.latest-title {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.5;
  margin-bottom: 8px;
}

.latest-sub {
  font-size: 11px;
  color: var(--ink-faint);
}

a {
  color: var(--pink-deep);
  text-decoration: none;
  font-weight: 700;
}
a:hover {
  text-decoration: underline;
}

.pending-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pending-num {
  font-size: 38px;
  font-weight: 700;
  line-height: 1;
  color: var(--ink-faint);
  transition: color 0.3s ease;
}

.pending-num.hot {
  color: var(--amber);
  text-shadow: 0 0 16px rgba(251, 191, 36, 0.35);
}

.pending-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--ink-dim);
}

.empty-note {
  font-size: 13px;
  color: var(--ink-faint);
  padding: 8px 0;
}

/* 加载 / 报错：吉祥物出场 */
.loading-panel {
  padding: 44px 20px;
}

.loading-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.mascot-box {
  width: 130px;
  height: 110px;
  flex: none;
}

.loading-inner .mascot-box {
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 8px 20px rgba(105, 161, 150, 0.15);
}

.err-inner .mascot-box {
  width: 110px;
  height: 94px;
  border-radius: 14px;
  overflow: hidden;
  flex: none;
}

.loading-text {
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-dim);
  letter-spacing: 0.06em;
}

.err-panel {
  border-color: #fecdd3;
  padding: 26px 28px;
}

.err-inner {
  display: flex;
  align-items: center;
  gap: 22px;
}

.err-title {
  color: #e11d48;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.err-detail {
  font-size: 12px;
  margin-bottom: 6px;
  color: var(--ink);
  word-break: break-all;
}

.err-hint {
  font-size: 12px;
  color: var(--ink-dim);
  line-height: 1.7;
}

@media (max-width: 900px) {
  .g-metrics,
  .g-main {
    grid-template-columns: 1fr;
  }
  .err-inner {
    flex-direction: column;
    text-align: center;
  }
}
</style>