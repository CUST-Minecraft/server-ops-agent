<script setup lang="ts">
defineProps<{ route: string }>()

const tabs = [
  { key: 'overview', label: '总览', href: '#/' },
  { key: 'incidents', label: '工单', href: '#/incidents' },
  { key: 'approvals', label: '审批', href: '#/approvals' },
]
</script>

<template>
  <nav class="tabs">
    <a v-for="t in tabs" :key="t.key" :href="t.href" class="tab" :class="{ active: route === t.key }">
      {{ t.label }}
    </a>
  </nav>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: 6px;
  margin-left: 8px;
}

.tab {
  padding: 7px 18px;
  text-decoration: none;
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-dim);
  border-radius: 999px;
  border: 2px solid transparent;
  transition: all 0.18s ease;
}

.tab:hover {
  color: var(--pink-deep);
  background: var(--pink-soft);
}

.tab.active {
  color: var(--pink-deep);
  background: var(--pink-soft);
  border-color: var(--line-strong);
}
</style>