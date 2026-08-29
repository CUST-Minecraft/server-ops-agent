<script setup lang="ts">
import { onMounted, ref } from 'vue'
import exp1 from '../assets/mascot-expressions/exp1.gif'
import exp2 from '../assets/mascot-expressions/exp2.gif'
import exp3 from '../assets/mascot-expressions/exp3.gif'
import exp4 from '../assets/mascot-expressions/exp4.gif'

const expressions = [exp1, exp2, exp3, exp4]

const idx = ref(0)

onMounted(() => {
  idx.value = Math.floor(Math.random() * expressions.length)
})
</script>

<template>
  <img class="mascot" :src="expressions[idx]" alt="吉祥物" />
</template>

<style scoped>
.mascot {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>