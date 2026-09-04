<script setup lang="ts">
import { ref } from 'vue'
import { api, saveSession } from '../api'
import { toast } from '../toast'
import MascotGif from './MascotGif.vue'

const username = ref('')
const password = ref('')
const busy = ref(false)

async function doLogin(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    toast('请输入用户名和密码', 'info')
    return
  }
  busy.value = true
  try {
    const payload = await api.login(username.value.trim(), password.value)
    saveSession(payload.token, username.value.trim())
    toast(`欢迎回来，${username.value.trim()}`, 'ok')
    window.location.hash = '#/'
  } catch (e) {
    toast(`登录失败：${e instanceof Error ? e.message : String(e)}`, 'err')
  } finally {
    password.value = ''
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login-card rise">
      <div class="login-mascot"><MascotGif /></div>
      <h1 class="login-title">值班登录 <span class="sparkle">✦</span></h1>
      <p class="login-sub">ServerOpsAgent 值班台 · 实名操作留痕</p>

      <form class="login-form" @submit.prevent="void doLogin()">
        <label class="field">
          <span class="field-label">用户名</span>
          <input v-model="username" class="field-input num" type="text" autocomplete="username"
                 placeholder="operator" />
        </label>
        <label class="field">
          <span class="field-label">密码</span>
          <input v-model="password" class="field-input num" type="password" autocomplete="current-password"
                 placeholder="••••••••" />
        </label>
        <button class="btn ok login-btn" type="submit" :disabled="busy" :class="{ busy }">
          {{ busy ? '登录中…' : '进入值班台' }}
        </button>
      </form>

      <p class="login-hint num">登录后可查看值班数据并执行审批；Token 关闭浏览器标签页后失效</p>
    </div>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 34px 32px 26px;
  box-shadow: 0 1px 2px rgba(58, 68, 66, 0.03), 0 12px 32px rgba(105, 161, 150, 0.1);
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.login-mascot {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid var(--pink-soft);
  box-shadow: 0 2px 10px rgba(105, 161, 150, 0.25);
  background: #fff;
  margin-bottom: 16px;
}

.login-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
}

.sparkle {
  color: var(--pink-deep);
  font-size: 15px;
  vertical-align: 2px;
}

.login-sub {
  font-size: 12px;
  color: var(--ink-faint);
  margin: 6px 0 22px;
}

.login-form {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: left;
}

.field-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--ink-faint);
}

.field-input {
  font-size: 14px;
  padding: 10px 14px;
  border-radius: 12px;
  border: 2px solid var(--line-strong);
  background: var(--panel-2);
  color: var(--ink);
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.field-input:focus {
  border-color: var(--pink);
  box-shadow: 0 0 0 3px var(--pink-soft);
}

.login-btn {
  margin-top: 6px;
  width: 100%;
  justify-content: center;
}

.login-hint {
  margin-top: 18px;
  font-size: 11px;
  color: var(--ink-faint);
  line-height: 1.5;
}
</style>
