<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api, type Incident } from '../api'
import { relTime } from '../format'
import { toast } from '../toast'

const incidents = ref<Incident[]>([])
const loading = ref(true)
const error = ref('')
let timer: number | undefined

async function load(): Promise<void> {
  try {
    error.value = ''
    const payload = await api.incidents()
    incidents.value = payload.incidents
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    toast(`工单获取失败：${error.value}`, 'err')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  timer = window.setInterval(() => void load(), 30000)
})
onUnmounted(() => window.clearInterval(timer))

function openDetail(id: number): void {
  window.location.hash = `#/incidents/${id}`
}
</script>

<template>
  <div class="incidents">
    <div class="head rise">
      <h1 class="head-title">工单</h1>
      <p class="head-sub num">最近 20 张</p>
    </div>

    <div class="panel table-panel rise" style="animation-delay: 0.05s">
      <div v-if="loading && !incidents.length" class="table-loading">
        <div v-for="i in 5" :key="i" class="skeleton" style="height: 36px; margin-bottom: 10px"></div>
      </div>

      <div v-else-if="error && !incidents.length" class="table-empty">
        <p class="err-title num">✕ 工单数据获取失败</p>
        <p class="err-body num">{{ error }}</p>
      </div>

      <div v-else-if="!incidents.length" class="table-empty">
        <span class="dot on"></span>
        <p class="empty-main">暂无工单</p>
        <p class="empty-sub num">检测器未触发，或所有异常已解决</p>
      </div>

      <table v-else class="tbl">
        <thead>
          <tr>
            <th class="th-id">#</th>
            <th>状态</th>
            <th>级别</th>
            <th class="th-title">标题</th>
            <th>开启</th>
            <th>解决</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(i, idx) in incidents" :key="i.id" class="trow rise" :style="{ animationDelay: `${0.04 + idx * 0.025}s` }" @click="openDetail(i.id)">
            <td class="td-id num">#{{ i.id }}</td>
            <td><span class="pill" :class="i.status">{{ i.status }}</span></td>
            <td><span class="tag" :class="i.severity">{{ i.severity }}</span></td>
            <td class="td-title">{{ i.title }}</td>
            <td class="td-time num">{{ relTime(i.opened_at) }}</td>
            <td class="td-time num">{{ i.resolved_at ? relTime(i.resolved_at) : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.incidents {
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

.table-panel {
  padding: 6px 0 0;
  overflow: hidden;
}

.tbl {
  width: 100%;
  border-collapse: collapse;
}

.tbl th {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-faint);
  text-align: left;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  background: var(--panel-2);
}

.tbl td {
  padding: 13px 18px;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
  vertical-align: middle;
}

.trow {
  transition: background 0.15s ease;
  cursor: pointer;
}

.trow:hover {
  background: var(--panel-2);
}

.trow:hover .td-id {
  color: var(--pink-deep);
}

.trow:last-child td {
  border-bottom: none;
}

.th-id,
.td-id {
  width: 70px;
}

.td-id {
  font-size: 12px;
  font-weight: 500;
  color: var(--teal);
  transition: color 0.15s ease;
}

.th-title,
.td-title {
  min-width: 240px;
}

.td-time {
  font-size: 12px;
  color: var(--ink-dim);
  white-space: nowrap;
}

.table-loading {
  padding: 18px;
}

.table-empty {
  padding: 48px 20px;
  text-align: center;
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
}

.err-body {
  font-size: 12px;
  color: var(--ink-dim);
}
</style>