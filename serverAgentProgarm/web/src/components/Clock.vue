<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { fmtClock, fmtDate } from '../format'

const now = ref(new Date())
let timer: number | undefined

onMounted(() => {
  timer = window.setInterval(() => {
    now.value = new Date()
  }, 1000)
})
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="clock">
    <span class="clock-date num">{{ fmtDate(now) }}</span>
    <span class="clock-time num">{{ fmtClock(now) }}</span>
  </div>
</template>

<style scoped>
.clock {
  display: flex;
  align-items: baseline;
  gap: 10px;
  color: var(--ink-dim);
}
.clock-date {
  font-size: 11px;
  letter-spacing: 0.08em;
}
.clock-time {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--pink-deep);
}
</style>