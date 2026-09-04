<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import TabNav from './components/TabNav.vue'
import OverviewView from './components/OverviewView.vue'
import IncidentsView from './components/IncidentsView.vue'
import IncidentDetailView from './components/IncidentDetailView.vue'
import ApprovalsView from './components/ApprovalsView.vue'
import ChatView from './components/ChatView.vue'
import LoginView from './components/LoginView.vue'
import Clock from './components/Clock.vue'
import MascotGif from './components/MascotGif.vue'
import { toastState, toast } from './toast'
import { getUsername, hasActiveSession, clearSession, api, AUTH_EVENT } from './api'

type Route =
  | { name: 'overview' | 'incidents' | 'approvals' | 'chat' | 'login' }
  | { name: 'detail'; id: string }

const route = ref<Route>({ name: 'login' })
const username = ref(getUsername())

const TAB_NAMES = ['overview', 'incidents', 'approvals', 'chat'] as const

function parseHash(): void {
  username.value = getUsername()
  const h = location.hash.replace(/^#\/?/, '').split('?')[0]
  if (h === 'login') {
    if (hasActiveSession()) {
      window.location.hash = '#/'
      return
    }
    route.value = { name: 'login' }
    return
  }
  if (!hasActiveSession()) {
    route.value = { name: 'login' }
    window.location.hash = '#/login'
    return
  }
  const m = h.match(/^incidents\/(\d+)$/)
  if (m) {
    route.value = { name: 'detail', id: m[1] }
    return
  }
  if ((TAB_NAMES as readonly string[]).includes(h)) {
    route.value = { name: h as 'overview' | 'incidents' | 'approvals' | 'chat' }
    return
  }
  route.value = { name: 'overview' }
}

function tabActive(): string {
  return route.value.name === 'detail' ? 'incidents' : route.value.name
}

function onAuth(e: Event): void {
  const msg = (e as CustomEvent<{ msg: string }>).detail?.msg
  username.value = null
  if (msg) toast(msg, 'info')
  if (route.value.name !== 'login') window.location.hash = '#/login'
}

async function doLogout(): Promise<void> {
  try {
    await api.logout()
  } catch {
    /* 后端未实现登出时忽略，本地会话照清 */
  }
  clearSession()
  username.value = null
  toast('已登出', 'info')
  window.location.hash = '#/login'
}

onMounted(() => {
  parseHash()
  window.addEventListener('hashchange', parseHash)
  window.addEventListener(AUTH_EVENT, onAuth)
})
onUnmounted(() => {
  window.removeEventListener('hashchange', parseHash)
  window.removeEventListener(AUTH_EVENT, onAuth)
})
</script>

<template>
  <LoginView v-if="route.name === 'login'" />

  <div v-else class="shell">
    <header class="topbar">
      <a class="brand" href="#/">
        <div class="brand-avatar"><MascotGif /></div>
        <span class="brand-name">ServerOps<span class="brand-accent">Agent</span></span>
        <span class="brand-sub">值班台 ✦</span>
      </a>
      <TabNav v-if="username" :route="tabActive()" />
      <div class="topbar-right">
        <template v-if="username">
          <span class="who num">👤 {{ username }}</span>
          <button class="btn mini" @click="void doLogout()">登出</button>
        </template>
        <a v-else class="btn mini" href="#/login">登录</a>
        <Clock />
      </div>
    </header>

    <main class="stage">
      <Transition name="view" mode="out-in">
        <component
          :is="route.name === 'overview' ? OverviewView
            : route.name === 'incidents' ? IncidentsView
            : route.name === 'approvals' ? ApprovalsView
            : route.name === 'chat' ? ChatView
            : IncidentDetailView"
          :key="route.name === 'detail' ? `detail-${route.id}` : route.name"
          :incident-id="route.name === 'detail' ? route.id : undefined"
        />
      </Transition>
    </main>

    <footer class="foot">
      <span>ServerOpsAgent ✦ 前后端分离门面</span>
      <span class="foot-hint">数据源：MySQL 共享总线 · /api/*</span>
    </footer>
  </div>

  <div class="toasts" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in toastState.items" :key="t.id" class="toast" :class="`toast-${t.kind}`">
        <span class="toast-mark num">{{ t.kind === 'ok' ? '✓' : t.kind === 'err' ? '✕' : 'ℹ' }}</span>
        <span class="toast-text num">{{ t.text }}</span>
      </div>
    </TransitionGroup>
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
  display: flex;
  align-items: center;
  gap: 10px;
}

.who {
  font-size: 12px;
  font-weight: 600;
  color: var(--teal-deep);
}

.btn.mini {
  font-size: 12px;
  padding: 5px 14px;
  border-radius: 999px;
  border: 2px solid var(--line-strong);
  background: var(--panel);
  color: var(--ink-dim);
  cursor: pointer;
  box-shadow: 0 3px 0 var(--line-strong);
  transition: all 0.15s ease;
  position: relative;
  top: 0;
  text-decoration: none;
}
.btn.mini:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 0 var(--line-strong);
  color: var(--pink-deep);
  border-color: var(--pink);
}
.btn.mini:active {
  top: 2px;
  box-shadow: 0 1px 0 var(--line-strong);
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
