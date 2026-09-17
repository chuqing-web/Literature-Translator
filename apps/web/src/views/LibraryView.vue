<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { FileUp, RefreshCw, Trash2, ArrowUpRight, FileText } from '@lucide/vue'
import { api, type DocumentItem } from '../api/client'
import { t } from '../i18n'

const router = useRouter()
const docs = ref<DocumentItem[]>([])
const busy = ref(false)
const error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const readyCount = computed(() => docs.value.filter((d) => d.status === 'ready').length)
const pageTotal = computed(() => docs.value.reduce((n, d) => n + (d.page_count || 0), 0))

async function refresh() {
  docs.value = await api.listDocuments()
}

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    const doc = await api.uploadDocument(file)
    await refresh()
    router.push(`/read/${doc.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
    input.value = ''
  }
}

async function remove(id: string) {
  await api.deleteDocument(id)
  await refresh()
}

function formatDate(iso: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

onMounted(() => {
  refresh().catch((err) => {
    error.value = err instanceof Error ? err.message : String(err)
  })
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">{{ t('libEyebrow') }}</p>
        <h1 class="hero-title">{{ t('libTitle') }}</h1>
        <p class="lead">{{ t('libLead') }}</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-ghost" @click="refresh">
          <RefreshCw :size="16" />
          {{ t('libRefresh') }}
        </button>
        <button class="btn btn-primary" :disabled="busy" @click="fileInput?.click()">
          <FileUp :size="16" />
          {{ busy ? t('libUploading') : t('libUpload') }}
        </button>
        <input ref="fileInput" type="file" accept="application/pdf" hidden @change="onFile" />
      </div>
    </div>

    <p v-if="error" class="alert">{{ error }}</p>

    <div v-if="docs.length" class="stats-row">
      <div class="stat-chip">
        <div class="label">{{ t('libDocuments') }}</div>
        <div class="value">{{ docs.length }}</div>
      </div>
      <div class="stat-chip">
        <div class="label">{{ t('libReady') }}</div>
        <div class="value">{{ readyCount }}</div>
      </div>
      <div class="stat-chip">
        <div class="label">{{ t('libPages') }}</div>
        <div class="value">{{ pageTotal }}</div>
      </div>
    </div>

    <div v-if="docs.length" class="lib-table">
      <div class="lib-table-head">
        <span>{{ t('libColDocument') }}</span>
        <span>{{ t('libColPages') }}</span>
        <span>{{ t('libColStatus') }}</span>
        <span style="text-align: right">{{ t('libColActions') }}</span>
      </div>
      <div v-for="doc in docs" :key="doc.id" class="doc-row">
        <div>
          <h3 class="doc-title">{{ doc.title || doc.filename }}</h3>
          <div class="doc-sub">{{ doc.filename }} · {{ formatDate(doc.created_at) }}</div>
        </div>
        <div class="muted" style="font-variant-numeric: tabular-nums">{{ doc.page_count }}</div>
        <div>
          <span class="badge" :class="doc.status">{{ doc.status.replaceAll('_', ' ') }}</span>
        </div>
        <div class="doc-actions">
          <button class="btn" @click="router.push(`/read/${doc.id}`)">
            {{ t('libOpen') }}
            <ArrowUpRight :size="15" />
          </button>
          <button class="btn btn-ghost btn-danger btn-icon" :title="t('libDelete')" @click="remove(doc.id)">
            <Trash2 :size="15" />
          </button>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <div class="empty-icon">
        <FileText :size="22" />
      </div>
      <h3>{{ t('libEmptyTitle') }}</h3>
      <p class="muted" style="margin: 0 0 1.1rem">{{ t('libEmptyLead') }}</p>
      <button class="btn btn-primary" :disabled="busy" @click="fileInput?.click()">
        <FileUp :size="16" />
        {{ t('libUploadFirst') }}
      </button>
    </div>
  </div>
</template>
