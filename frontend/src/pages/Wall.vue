<template>
  <div class="wall">
    <h1 class="serif">愿望墙</h1>
    <p class="tag">置顶整块在前 · 区内新到旧 · 点卡片进详情</p>
    <p v-if="err" class="err">{{ err }}</p>

    <section v-if="pinned.length">
      <p class="band-title">📌 置顶区 · {{ pinned.length }}</p>
      <div class="masonry">
        <article v-for="w in pinned" :key="w.id"
          :class="['card', 'pinned', isGrey(w) ? 'grey' : '']"
          @click="$router.push('/wishes/' + w.id)">
          <span class="pin-badge">📌</span>
          <h3>{{ w.title || '（无标题）' }}</h3>
          <p>{{ w.note }}</p>
          <span class="tag">{{ w.status }} · {{ w.data_quality }}</span><br />
          <button class="pin-btn ghost" @click.stop="togglePin(w)">取消置顶</button>
        </article>
      </div>
    </section>

    <section>
      <p v-if="pinned.length" class="band-title">普通区</p>
      <div class="masonry">
        <article v-for="w in rest" :key="w.id" class="card"
          @click="$router.push('/wishes/' + w.id)">
          <h3>{{ w.title || '（无标题）' }}</h3>
          <p>{{ w.note }}</p>
          <span class="tag">{{ w.status }} · {{ w.data_quality }}</span><br />
          <button v-if="w.status === 'open'" class="pin-btn ghost" @click.stop="togglePin(w)">📌 置顶</button>
        </article>
      </div>
    </section>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
const rows = ref([])
const err = ref('')
// Ordering is the server projection's single source of truth; here we only split bands.
const pinned = computed(() => rows.value.filter(w => w.pinned))
const rest = computed(() => rows.value.filter(w => !w.pinned))
function isGrey(w) { return w.pinned && (w.status === 'claimed' || w.status === 'fulfilled') }
async function load() {
  err.value = ''
  try { rows.value = await api('/wishes') } catch (e) { err.value = e.message }
}
async function togglePin(w) {
  err.value = ''
  try {
    await api('/wishes/' + w.id + (w.pinned ? '/unpin' : '/pin'), { method: 'POST', body: '{}' })
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
