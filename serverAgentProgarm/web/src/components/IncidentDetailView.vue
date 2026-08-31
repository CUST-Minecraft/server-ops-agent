<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api, type IncidentDetailPayload, type InvestigationEntry } from '../api'
import { fmtDateTime } from '../format'
import { toast } from '../toast'

const props = defineProps<{ incidentId: string }>()

const data = ref<IncidentDetailPayload | null>(null)
const loading = ref(true)
const error = ref('')

async function load(): Promise<void> {
  const id = Number(props.incidentId)
  if (!Number.isFinite(id)) {
    error.value = '单子编号无效'
    loading.value = false
    return
  }
  try {
    error.value = ''
    data.value = await api.incident(id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    toast(`单子详情获取失败：${error.value}`, 'err')
  } finally {
    loading.value = false
  }
}

watch(() => props.incidentId, () => { loading.value = true; void load() })
onMounted(() => void load())

function confClass(conf?: string): string {
  if (conf === 'high') return 'conf-high'
  if (conf === 'low') return 'conf-low'
  return 'conf-mid'
}

function hasAction(h: InvestigationEntry): boolean {
  return !!h.conclusion.suggested_action && !!h.conclusion.suggested_action!.command
}
</script>

<template>
  <div class="detail">
    <!-- 顶部：标题 + 状态徽章 -->
    <div class="head rise">
      <a class="back num" href="#/incidents">← 工单列表</a>
      <h1 class="head-title num" v-if="data">#{{ data.inc.id }}</h1>
      <p class="head-sub" v-if="data">{{ data.inc.title }}</p>
    </div>

    <!-- 基本信息卡片 -->
    <div v-if="data" class="panel meta-card rise" style="animation-delay: 0.05s">
      <div class="meta-row">
        <span class="pill" :class="data.inc.status">{{ data.inc.status }}</span>
        <span class="tag" :class="data.inc.severity">{{ data.inc.severity }}</span>
        <span class="meta-kind num">{{ data.inc.kind }}</span>
        <span class="meta-time num">开启 {{ fmtDateTime(data.inc.opened_at) }}</span>
        <span v-if="data.inc.resolved_at" class="meta-time num resolved">解决 {{ fmtDateTime(data.inc.resolved_at) }}</span>
      </div>

      <!-- 状态记录：时间线 -->
      <div class="notes-block">
        <p class="notes-label">状态记录</p>
        <ol v-if="data.notes.length" class="notes-list">
          <li v-for="(n, i) in data.notes" :key="i" class="note-item">
            <span class="note-dot" :class="{ first: i === 0 }"></span>
            <span class="note-text">{{ n }}</span>
          </li>
        </ol>
        <p v-else class="notes-empty">无状态记录</p>
      </div>
    </div>

    <!-- 加载 / 错误 / 空态 -->
    <div v-if="loading && !data" class="panel rise" style="animation-delay: 0.05s">
      <div class="skeleton" style="height: 90px; margin-bottom: 12px"></div>
      <div class="skeleton" style="height: 90px"></div>
    </div>

    <div v-else-if="error && !data" class="panel empty-panel rise" style="animation-delay: 0.05s">
      <p class="err-title num">✕ 单子详情获取失败</p>
      <p class="err-body num">{{ error }}</p>
      <a class="btn" href="#/incidents">返回工单列表</a>
    </div>

    <!-- 调查历史：每次调查一张卡片 -->
    <template v-if="data">
      <div v-if="data.history.length" class="inv-head-row rise" style="animation-delay: 0.08s">
        <p class="inv-head-label num">调查记录 · {{ data.history.length }} 次</p>
        <span class="inv-head-hint num">含重试，每次独立留痕</span>
      </div>

      <div v-else class="panel empty-panel rise" style="animation-delay: 0.08s">
        <span class="dot on"></span>
        <p class="empty-main">无调查记录</p>
        <p class="empty-sub num">该单子尚未产生调查过程，或已由旧流程处理</p>
      </div>

      <TransitionGroup name="card" tag="div" class="inv-list">
        <div v-for="(h, idx) in data.history" :key="h.attempt" class="panel inv-card rise" :style="{ animationDelay: `${0.1 + idx * 0.06}s` }">
          <!-- 卡头：第几次 + 时间 -->
          <div class="inv-head">
            <span class="inv-num num">调查 #{{ h.attempt }}</span>
            <span class="inv-at num">{{ fmtDateTime(h.at) }}</span>
          </div>

          <!-- 结论 -->
          <div class="conclusion">
            <p class="label">结论</p>
            <p class="root-cause">{{ h.conclusion.root_cause || '（无结论）' }}</p>
            <div class="conclusion-meta">
              <span class="conf" :class="confClass(h.conclusion.confidence)">
                置信度 {{ h.conclusion.confidence || '—' }}
              </span>
              <span v-if="h.conclusion.recommended_runbook" class="rb-name num">
                → 预案: {{ h.conclusion.recommended_runbook }}
              </span>
            </div>
          </div>

          <!-- 有预案 -->
          <div v-if="h.conclusion.recommended_runbook" class="block rb-block">
            <p class="label">推荐预案（自动执行 / 待审批）</p>
            <p class="rb-text num">{{ h.conclusion.recommended_runbook }}</p>
          </div>

          <!-- 无预案但有建议 -->
          <div v-else-if="hasAction(h)" class="block act-block">
            <p class="label">建议（预案外，需人工分析执行）</p>
            <p class="act-desc">{{ h.conclusion.suggested_action!.description }}</p>
            <pre class="act-cmd num">{{ h.conclusion.suggested_action!.command }}</pre>
            <div class="act-meta">
              <p class="act-eff">预期效果: {{ h.conclusion.suggested_action!.expected_effect }}</p>
              <p v-if="h.conclusion.suggested_action!.risk_note" class="act-risk">风险: {{ h.conclusion.suggested_action!.risk_note }}</p>
            </div>
          </div>

          <!-- 无预案无建议 -->
          <div v-else class="block none-block">
            <p class="label">修复建议</p>
            <p class="none-text">无修复建议（根因已记录，待人工判断）</p>
          </div>

          <!-- 折叠轨迹 -->
          <details v-if="h.conclusion.trail && h.conclusion.trail.length" class="trail">
            <summary class="trail-summary num">
              <span class="trail-caret"></span>
              调查轨迹（{{ h.conclusion.trail.length }} 步）
            </summary>
            <div class="trail-table-wrap">
              <table class="trail-table">
                <thead>
                  <tr>
                    <th class="num">step</th>
                    <th>工具</th>
                    <th>参数</th>
                    <th>结果</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="t in h.conclusion.trail" :key="t.step">
                    <td class="num">{{ t.step }}</td>
                    <td class="tool num">{{ t.tool }}</td>
                    <td class="args num">{{ JSON.stringify(t.args) }}</td>
                    <td class="summary num">{{ t.summary }}</td>
                    <td><span class="st" :class="`st-${t.status}`">{{ t.status }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        </div>
      </TransitionGroup>
    </template>
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.head {
  display: flex;
  align-items: baseline;
  gap: 14px;
  flex-wrap: wrap;
}

.back {
  font-size: 13px;
  font-weight: 700;
  color: var(--teal-deep);
  text-decoration: none;
  padding: 6px 14px;
  border: 2px solid var(--line-strong);
  border-radius: 999px;
  background: var(--panel);
  box-shadow: 0 3px 0 var(--line-strong);
  transition: all 0.15s ease;
  position: relative;
  top: 0;
}
.back:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 0 var(--line-strong);
  color: var(--pink-deep);
  border-color: var(--pink);
}
.back:active {
  top: 2px;
  box-shadow: 0 1px 0 var(--line-strong);
}

.head-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--ink);
}

.head-sub {
  font-size: 14px;
  color: var(--ink-dim);
}

/* —— 基本信息卡片 —— */
.meta-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.meta-kind {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--ink-faint);
  border: 1px solid var(--line);
  padding: 2px 10px;
  border-radius: 6px;
}

.meta-time {
  font-size: 11px;
  color: var(--ink-dim);
  margin-left: auto;
}
.meta-time.resolved {
  margin-left: 0;
}

/* —— 状态记录时间线 —— */
.notes-block {
  border-top: 1px dashed var(--line-strong);
  padding-top: 14px;
}

.notes-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--ink-faint);
  margin-bottom: 10px;
}

.notes-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.note-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.note-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--line-strong);
  margin-top: 6px;
  flex: none;
}
.note-dot.first {
  background: var(--teal);
  box-shadow: 0 0 0 3px var(--teal-soft);
}

.note-text {
  font-size: 12px;
  color: var(--ink-dim);
  line-height: 1.6;
}

.notes-empty {
  font-size: 12px;
  color: var(--ink-faint);
}

/* —— 调查卡片列表 —— */
.inv-head-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-top: 4px;
}

.inv-head-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--ink);
}

.inv-head-hint {
  font-size: 11px;
  color: var(--ink-faint);
}

.inv-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.inv-card {
  border-left: 4px solid var(--teal);
}

.inv-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.inv-num {
  font-size: 14px;
  font-weight: 700;
  color: var(--teal-deep);
  letter-spacing: 0.02em;
}

.inv-at {
  font-size: 11px;
  color: var(--ink-faint);
  margin-left: auto;
}

/* —— 结论 —— */
.conclusion {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 12px;
}

.label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--ink-faint);
  text-transform: uppercase;
  margin-bottom: 6px;
}

.root-cause {
  font-size: 14px;
  font-weight: 500;
  color: var(--ink);
  line-height: 1.6;
}

.conclusion-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.conf {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 999px;
}
.conf-high { color: #059669; background: #d1fae5; }
.conf-mid  { color: #d97706; background: #fef3c7; }
.conf-low  { color: #e11d48; background: #ffe4e6; }

.rb-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--teal-deep);
}

/* —— 预案 / 建议 / 无建议 —— */
.block {
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 12px;
}

.rb-block {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
}

.rb-text {
  font-size: 13px;
  font-weight: 600;
  color: #047857;
}

.act-block {
  background: #fffbeb;
  border: 1px solid #fde68a;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.act-desc {
  font-size: 13px;
  color: var(--ink);
  line-height: 1.6;
}

.act-cmd {
  font-family: var(--mono);
  font-size: 12.5px;
  line-height: 1.6;
  color: #92400e;
  background: var(--panel);
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.act-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.act-eff {
  font-size: 12px;
  color: var(--ink-dim);
}

.act-risk {
  font-size: 12px;
  color: #b45309;
}

.none-block {
  background: var(--panel-2);
  border: 1px dashed var(--line-strong);
}

.none-text {
  font-size: 12.5px;
  color: var(--ink-dim);
}

/* —— 折叠轨迹 —— */
.trail {
  border-top: 1px dashed var(--line);
  padding-top: 10px;
}

.trail-summary {
  font-size: 12px;
  font-weight: 700;
  color: var(--teal-deep);
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  user-select: none;
}
.trail-summary::-webkit-details-marker {
  display: none;
}

.trail-caret {
  width: 0;
  height: 0;
  border-left: 5px solid var(--teal);
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  transition: transform 0.18s ease;
}
.trail[open] .trail-caret {
  transform: rotate(90deg);
}

.trail-table-wrap {
  margin-top: 10px;
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 10px;
}

.trail-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.trail-table th {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-faint);
  text-align: left;
  padding: 8px 12px;
  background: var(--panel-2);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}

.trail-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  color: var(--ink-dim);
  vertical-align: top;
}

.trail-table tr:last-child td {
  border-bottom: none;
}

.tool {
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
}

.args,
.summary {
  max-width: 260px;
  word-break: break-all;
  line-height: 1.5;
}

.st {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
  white-space: nowrap;
}
.st-success { color: #059669; background: #d1fae5; }
.st-error   { color: #e11d48; background: #ffe4e6; }
.st-unknown { color: var(--ink-dim); background: var(--panel-3); }

/* —— 空态 / 错误 —— */
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
}

.err-body {
  font-size: 12px;
  color: var(--ink-dim);
  margin-bottom: 6px;
}

/* —— 卡片过渡 —— */
.card-enter-active,
.card-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.card-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
.card-leave-to {
  opacity: 0;
  transform: translateX(18px);
}
.card-move {
  transition: transform 0.22s ease;
}
</style>