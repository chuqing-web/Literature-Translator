<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Columns2,
  Rows3,
  Languages,
  FileDown,
  RefreshCw,
} from '@lucide/vue'
import {
  api,
  type AssistantMessageItem,
  type BlockItem,
  type DocumentItem,
  type HighlightItem,
  type NoteItem,
} from '../api/client'
import PdfPage from '../components/PdfPage.vue'
import NotesPanel from '../components/NotesPanel.vue'
import AssistantPanel from '../components/AssistantPanel.vue'
import { t } from '../i18n'

const props = defineProps<{ id: string }>()
const router = useRouter()

const doc = ref<DocumentItem | null>(null)
const mode = ref<'embedded' | 'side'>('embedded')
const pageIndex = ref(0)
const blocksByPage = ref<Record<number, BlockItem[]>>({})
const notes = ref<NoteItem[]>([])
const highlights = ref<HighlightItem[]>([])
const selectedBlock = ref<BlockItem | null>(null)
const translating = ref(false)
const jobInfo = ref('')
const error = ref('')
const scrollLeft = ref<HTMLElement | null>(null)
const scrollRight = ref<HTMLElement | null>(null)
const pageSize = ref<{ width: number; height: number } | null>(null)
const activeSyncId = ref<string | null>(null)
let syncing = false

const railTab = ref<'notes' | 'assistant'>('notes')
const assistantMessages = ref<AssistantMessageItem[]>([])
const assistantSending = ref(false)
const assistantError = ref('')
const assistantUseFull = ref(false)

const pdfUrl = computed(() => api.pdfUrl(props.id))
const pageCount = computed(() => doc.value?.page_count || 0)
const currentBlocks = computed(() => blocksByPage.value[pageIndex.value] || [])
const pageHighlights = computed(() =>
  highlights.value.filter((h) => h.page_index === pageIndex.value),
)
const translatableBlocks = computed(() =>
  currentBlocks.value.filter(
    (b) =>
      b.block_type === 'text' ||
      b.block_type === 'caption' ||
      b.block_type === 'heading' ||
      b.block_type === 'title' ||
      b.block_type === 'meta',
  ),
)
const translatedCount = computed(
  () => translatableBlocks.value.filter((b) => !!b.translation).length,
)

async function loadMeta() {
  doc.value = await api.getDocument(props.id)
  const settings = await api.getSettings()
  mode.value = settings.view_mode
  document.documentElement.style.setProperty('--font-trans', settings.font_family)
  document.documentElement.style.setProperty('--trans-size', `${settings.font_size}px`)
  document.documentElement.style.setProperty('--trans-leading', String(settings.line_height))
}

async function loadPage(page: number) {
  blocksByPage.value[page] = await api.pageBlocks(props.id, page)
  await nextTick()
}

async function loadNotes() {
  notes.value = await api.listNotes(props.id)
  highlights.value = await api.listHighlights(props.id)
}

async function reparse() {
  error.value = ''
  try {
    doc.value = await api.reparseDocument(props.id)
    blocksByPage.value = {}
    await loadPage(pageIndex.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

async function translateAll() {
  translating.value = true
  error.value = ''
  try {
    const { job } = await api.startTranslate(props.id)
    jobInfo.value = t('readerJobProgress', { done: job.done, total: job.total || '…' })
    const poll = async () => {
      const status = await api.jobStatus(job.id)
      jobInfo.value = t('readerJobStatus', {
        status: status.status,
        done: status.done,
        total: status.total,
      })
      if (status.error) {
        error.value = status.error
      }
      if (status.status === 'pending' || status.status === 'running') {
        await loadPage(pageIndex.value)
        setTimeout(poll, 800)
        return
      }
      translating.value = false
      if (status.error) error.value = status.error
      await loadPage(pageIndex.value)
    }
    setTimeout(poll, 500)
  } catch (err) {
    translating.value = false
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function onSourceRendered(payload: { width: number; height: number }) {
  pageSize.value = payload
}

async function saveTranslation(payload: { blockId: string; text: string }) {
  const updated = await api.updateTranslation(payload.blockId, payload.text)
  const list = blocksByPage.value[pageIndex.value] || []
  const idx = list.findIndex((b) => b.id === updated.id)
  if (idx >= 0) list[idx] = updated
}

async function onSelectBlock(block: BlockItem) {
  selectedBlock.value = block
  activeSyncId.value = block.id
  const exists = highlights.value.find((h) => h.block_id === block.id)
  if (!exists && !block.block_type.startsWith('placeholder')) {
    const hl = await api.createHighlight(props.id, {
      page_index: block.page_index,
      block_id: block.id,
    })
    highlights.value.push(hl)
  }
}

async function addNote(content: string) {
  const note = await api.createNote(props.id, {
    content,
    page_index: selectedBlock.value?.page_index ?? pageIndex.value,
    block_id: selectedBlock.value?.id ?? null,
  })
  notes.value.unshift(note)
}

async function removeNote(noteId: string) {
  await api.deleteNote(props.id, noteId)
  notes.value = notes.value.filter((n) => n.id !== noteId)
}

async function loadAssistant() {
  const data = await api.listAssistantMessages(props.id)
  assistantMessages.value = data.messages
}

async function sendAssistant(content: string) {
  assistantSending.value = true
  assistantError.value = ''
  try {
    const res = await api.chatAssistant(props.id, {
      content,
      context_mode: assistantUseFull.value ? 'full' : 'auto',
      page_index: selectedBlock.value?.page_index ?? pageIndex.value,
      block_id: assistantUseFull.value ? null : selectedBlock.value?.id ?? null,
    })
    assistantMessages.value = [
      ...assistantMessages.value,
      res.user_message,
      res.assistant_message,
    ]
  } catch (err) {
    assistantError.value = err instanceof Error ? err.message : String(err)
  } finally {
    assistantSending.value = false
  }
}

async function clearAssistant() {
  if (!assistantMessages.value.length) return
  try {
    await api.clearAssistantMessages(props.id)
    assistantMessages.value = []
    assistantError.value = ''
  } catch (err) {
    assistantError.value = err instanceof Error ? err.message : String(err)
  }
}

function prevPage() {
  if (pageIndex.value > 0) pageIndex.value -= 1
}

function nextPage() {
  if (pageIndex.value < pageCount.value - 1) pageIndex.value += 1
}

/** Dual PdfPage canvases share height — mirror scrollTop 1:1. */
function syncScroll(from: 'left' | 'right') {
  if (mode.value !== 'side' || syncing) return
  const src = from === 'left' ? scrollLeft.value : scrollRight.value
  const dst = from === 'left' ? scrollRight.value : scrollLeft.value
  if (!src || !dst) return
  if (Math.abs(src.scrollTop - dst.scrollTop) < 1) return
  syncing = true
  dst.scrollTop = src.scrollTop
  requestAnimationFrame(() => {
    syncing = false
  })
}

async function toggleMode() {
  mode.value = mode.value === 'embedded' ? 'side' : 'embedded'
  await api.putSettings({ view_mode: mode.value })
}

watch(pageIndex, (p) => {
  pageSize.value = null
  activeSyncId.value = null
  loadPage(p).catch((e) => {
    error.value = e instanceof Error ? e.message : String(e)
  })
})

onMounted(async () => {
  try {
    await loadMeta()
    await loadPage(0)
    await loadNotes()
    await loadAssistant()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
})
</script>

<template>
  <div class="reader-layout" :class="{ 'is-side': mode === 'side' }">
    <div class="reader-main">
      <div class="reader-toolbar">
        <button class="btn btn-ghost" @click="router.push('/')">
          <ArrowLeft :size="16" />
          {{ t('readerLibrary') }}
        </button>
        <span class="toolbar-sep" />
        <span class="reader-title" :title="doc?.title || ''">{{ doc?.title || t('readerReading') }}</span>
        <span class="toolbar-sep" />
        <button
          class="btn btn-icon btn-ghost"
          :disabled="pageIndex <= 0"
          :title="t('readerPrev')"
          @click="prevPage"
        >
          <ChevronLeft :size="18" />
        </button>
        <span class="page-pill">{{ pageIndex + 1 }} / {{ pageCount || '—' }}</span>
        <button
          class="btn btn-icon btn-ghost"
          :disabled="pageIndex >= pageCount - 1"
          :title="t('readerNext')"
          @click="nextPage"
        >
          <ChevronRight :size="18" />
        </button>
        <span class="toolbar-sep" />
        <button class="btn" @click="toggleMode">
          <component :is="mode === 'embedded' ? Rows3 : Columns2" :size="15" />
          {{ mode === 'embedded' ? t('readerEmbedded') : t('readerSide') }}
        </button>
        <button class="btn" :title="t('readerReparse')" @click="reparse">
          <RefreshCw :size="15" />
          {{ t('readerReparse') }}
        </button>
        <button class="btn btn-primary" :disabled="translating" @click="translateAll">
          <Languages :size="15" />
          {{ translating ? t('readerTranslating') : t('readerTranslate') }}
        </button>
        <a class="btn" :href="api.exportDocxUrl(id)" target="_blank" rel="noopener">
          <FileDown :size="15" />
          {{ t('readerWord') }}
        </a>
        <span v-if="jobInfo" class="job-chip">{{ jobInfo }}</span>
      </div>

      <p v-if="error" class="alert reader-alert">{{ error }}</p>
      <p v-if="doc?.status === 'unsupported_scan'" class="alert reader-alert">
        {{ doc.status_message }}
      </p>
      <p
        v-if="mode === 'side' && translatableBlocks.length"
        class="muted"
        style="margin: 0.4rem 0.85rem; font-size: 0.8rem"
      >
        {{ t('readerPageProgress', { done: translatedCount, total: translatableBlocks.length }) }}
      </p>

      <div v-if="mode === 'embedded'" class="pages">
        <PdfPage
          :pdf-url="pdfUrl"
          :page-index="pageIndex"
          :blocks="currentBlocks"
          :highlights="pageHighlights"
          mode="embedded"
          side="source"
          @select-block="onSelectBlock"
          @save-translation="saveTranslation"
        />
      </div>

      <div v-else class="pages side">
        <div ref="scrollLeft" @scroll="syncScroll('left')">
          <PdfPage
            :pdf-url="pdfUrl"
            :page-index="pageIndex"
            :blocks="[]"
            :highlights="pageHighlights"
            mode="side"
            side="source"
            @rendered="onSourceRendered"
            @select-block="onSelectBlock"
          />
        </div>
        <div ref="scrollRight" class="trans-scroll" @scroll="syncScroll('right')">
          <PdfPage
            v-if="pageSize"
            :pdf-url="pdfUrl"
            :page-index="pageIndex"
            :blocks="currentBlocks"
            :highlights="pageHighlights"
            :forced-width="pageSize.width"
            mode="side"
            side="translation"
            @select-block="onSelectBlock"
            @save-translation="saveTranslation"
          />
          <div v-else class="trans-pending">{{ t('readerAligning') }}</div>
        </div>
      </div>
    </div>

    <aside class="notes-rail">
      <div class="rail-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          class="rail-tab"
          :class="{ active: railTab === 'notes' }"
          :aria-selected="railTab === 'notes'"
          @click="railTab = 'notes'"
        >
          {{ t('railTabNotes') }}
        </button>
        <button
          type="button"
          role="tab"
          class="rail-tab"
          :class="{ active: railTab === 'assistant' }"
          :aria-selected="railTab === 'assistant'"
          @click="railTab = 'assistant'"
        >
          {{ t('railTabAssistant') }}
        </button>
      </div>
      <NotesPanel
        v-show="railTab === 'notes'"
        :notes="notes"
        :selected-block-id="selectedBlock?.id ?? null"
        :selected-page="selectedBlock?.page_index ?? pageIndex"
        @add="addNote"
        @remove="removeNote"
      />
      <AssistantPanel
        v-show="railTab === 'assistant'"
        :messages="assistantMessages"
        :sending="assistantSending"
        :error="assistantError"
        :use-full-doc="assistantUseFull"
        :selected-block-id="selectedBlock?.id ?? null"
        :selected-page="selectedBlock?.page_index ?? pageIndex"
        @send="sendAssistant"
        @clear="clearAssistant"
        @update:use-full-doc="assistantUseFull = $event"
      />
    </aside>
  </div>
</template>

<style scoped>
.trans-scroll {
  overflow: auto;
  max-height: calc(100vh - 72px);
  min-height: 0;
}
.trans-pending {
  padding: 2rem 1rem;
  color: var(--muted, #6b7685);
  font-size: 0.9rem;
  text-align: center;
}
</style>
