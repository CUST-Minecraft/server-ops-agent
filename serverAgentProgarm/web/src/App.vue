<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import TabNav from './components/TabNav.vue'
import OverviewView from './components/OverviewView.vue'
import IncidentsView from './components/IncidentsView.vue'
import ApprovalsView from './components/ApprovalsView.vue'
import Clock from './components/Clock.vue'
import MascotGif from './components/MascotGif.vue'
import { toastState } from './toast'

type Route = 'overview' | 'incidents' | 'approvals'

const route = ref<Route>('overview')

const ROUTES: Route[] = ['overview', 'incidents', 'approvals']

function parseHash(): void {
  const h = location.hash.replace(/^#\/?/, '').split('?')[0]
  route.value = (ROUTES as string[]).includes(h) ? (h as Route) : 'overview'
}

onMounted(() => {
  parseHash()
  window.addEventListener('hashchange', parseHash)
})
onUnmounted(() => window.removeEventListener('hashchange', parseHash))
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <a class="brand" href="#/">
        <div class="brand-avatar"><MascotGif /></div>
        <span class="brand-name">ServerOps<span class="brand-accent">Agent</span></span>
        <span class="brand-sub">值班台 ✦</span>
      </a>
      <TabNav :route="route" />
      <div class="topbar-right">
        <Clock />
      </div>
    </header>

    <main class="stage">
      <Transition name="view" mode="out-in">
        <component :is="route === 'overview' ? OverviewView
          : route === 'incidents' ? IncidentsView
          : ApprovalsView" :key="route" />
      </Transition>
    </main>

    <footer class="foot">
      <span>ServerOpsAgent ✦ 前后端分离门面</span>
      <span class="foot-hint">数据源：MySQL 共享总线 · /api/*</span>
    </footer>

    <div class="toasts" aria-live="polite">
      <TransitionGroup name="toast">
        <div v-for="t in toastState.items" :key="t.id" class="toast" :class="`toast-${t.kind}`">
          <span class="toast-mark num">{{ t.kind === 'ok' ? '✓' : t.kind === 'err' ? '✕' : 'ℹ' }}</span>
          <span class="toast-text num">{{ t.text }}</span>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 32px;
  height: 64px;
  border-bottom: 2px solid var(--line);
  background: rgba(255, 253, 254, 0.82);
  backdrop-filter: blur(10px);
  position: sticky;
  top: 0;
  z-index: 50;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  color: var(--ink);
  flex: none;
}

.brand-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid var(--pink-soft);
  box-shadow: 0 2px 8px rgba(105, 161, 150, 0.25);
  background: #fff;
  flex: none;
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.brand-accent {
  color: var(--pink-deep);
}

.brand-sub {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--ink-faint);
  margin-left: 4px;
}

.topbar-right {
  margin-left: auto;
  flex: none;
}

.stage {
  flex: 1;
  width: 100%;
  max-width: 1080px;
  margin: 0 auto;
  padding: 32px 32px 56px;
}

.foot {
  display: flex;
  justify-content: space-between;
  padding: 16px 32px;
  border-top: 2px solid var(--line);
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--ink-faint);
}

.toasts {
  position: fixed;
  top: 80px;
  right: 24px;
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 420px;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: var(--panel);
  border: 2px solid var(--line);
  border-left: 4px solid var(--pink);
  border-radius: 14px;
  padding: 10px 14px;
  box-shadow: 0 8px 24px rgba(105, 161, 150, 0.12);
}
.toast-ok { border-left-color: var(--mint-deep); }
.toast-ok .toast-mark { color: var(--mint-deep); }
.toast-err { border-left-color: var(--red); }
.toast-err .toast-mark { color: var(--red); }
.toast-info .toast-mark { color: var(--pink-deep); }

.toast-mark {
  font-size: 13px;
  line-height: 1.5;
}

.toast-text {
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink);
  word-break: break-all;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(20px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>