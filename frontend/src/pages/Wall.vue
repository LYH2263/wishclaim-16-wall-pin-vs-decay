<template>
  <div class="wall">
    <h1 class="serif">愿望墙</h1>
    <p class="tag">置顶区在先（先钉先顶） · 其余按创建时间衰减 · 点卡片认领</p>
    <div class="masonry">
      <article v-for="w in rows" :key="w.id" class="card"
               :class="{ pinned: w.pinned, graypin: w.pinned && !w.pin_active }"
               @click="$router.push('/wishes/'+w.id)">
        <h3><span v-if="w.pinned" class="pin-badge">📌</span>{{ w.title || '（无标题）' }}</h3>
        <p>{{ w.note }}</p>
        <span class="tag">{{ w.pinned ? (w.pin_active ? '置顶 · ' : '灰钉 · ') : '' }}{{ w.status }} · {{ w.data_quality }}</span>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
onMounted(async () => { rows.value = await api('/wishes') })
</script>
