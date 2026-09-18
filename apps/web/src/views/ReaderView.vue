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
  formatApiError,
  type AssistantMessageItem,
  type BlockItem,
  type DocumentItem,
  type HighlightItem,
  type NoteItem,
} from '../api/client'
import PdfPage from '../components/PdfPage.vue'
import NotesPanel from '../components/NotesPanel.vue'
import AssistantPanel, { type AssistantContextMode } from '../components/AssistantPanel.vue'
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
const assistantStreaming = ref('')
const assistantError = ref('')
const assistantContextMode = ref<AssistantContextMode>('page')
const notesBusy = ref(false)
const notesError = ref('')
let assistantAbort: AbortController | null = null

const pdfUrl = computed(() => api.pdfUrl(props.id))
const pageCount = computed(() => doc.value?.page_count || 0)
const currentBlocks = computed(() => blocksByPage.value[pageIndex.value] || [])
const pageHighlights = computed(() =>
  highlights.value.filter((h) => h.page_index === pageIndex.value),
)
const selectedSnippet = computed(() => {
  const block = selectedBlock.value
  if (!block) return null
  const raw = (block.translation || block.text || '').replace(/\s+/g, ' ').trim()
  if (!raw) return null
  return raw.length > 120 ? `${raw.slice(0, 118)}…` : raw
})
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
  if (assistantContextMode.value !== 'full') {
    assistantContextMode.value = 'block'
  }
}

function friendlyRailError(err: unknown, fallbackKey: 'notesErrGeneric' | 'assistantErrConnect'): string {
  const detail = formatApiError(err)
  if (/All connection attempts failed|ConnectError|ECONNREFUSED|ENOTFOUND/i.test(detail)) {
    return t('assistantErrConnect')
  }
  if (/No translation provider|No provider configured/i.test(detail)) {
    return t('assistantErrNoProvider')
  }
  if (/401|403|API key|Unauthorized|authentication/i.test(detail)) {
    return t('assistantErrAuth')
  }
  return detail || t(fallbackKey)
}

async function addNote(content: string) {
  notesBusy.value = true
  notesError.value = ''
  try {
    const note = await api.createNote(props.id, {
      content,
      page_index: selectedBlock.value?.page_index ?? pageIndex.value,
      block_id: selectedBlock.value?.id ?? null,
    })
    notes.value.unshift(note)
  } catch (err) {
    notesError.value = friendlyRailError(err, 'notesErrGeneric')
  } finally {
    notesBusy.value = false
  }
}

async function removeNote(noteId: string) {
  notesBusy.value = true
  notesError.value = ''
  try {
    await api.deleteNote(props.id, noteId)
    notes.value = notes.value.filter((n) => n.id !== noteId)
  } catch (err) {
    notesError.value = friendlyRailError(err, 'notesErrGeneric')
  } finally {
    notesBusy.value = false
  }
}

async function openNote(note: NoteItem) {
  notesError.value = ''
  pageIndex.value = note.page_index
  await loadPage(note.page_index)
  if (note.block_id) {
    const list = blocksByPage.value[note.page_index] || []
    const block = list.find((b) => b.id === note.block_id) || null
    selectedBlock.value = block
    activeSyncId.value = note.block_id
    if (block && assistantContextMode.value !== 'full') {
      assistantContextMode.value = 'block'
    }
  } else {
    selectedBlock.value = null
    activeSyncId.value = null
  }
  await nextTick()
  const target = document.querySelector(`[data-block-id="${note.block_id}"]`)
  target?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

async function loadAssistant() {
  const data = await api.listAssistantMessages(props.id)
  assistantMessages.value = data.messages
}

function stopAssistant() {
  assistantAbort?.abort()
  assistantAbort = null
  assistantSending.value = false
}

async function sendAssistant(content: string) {
  stopAssistant()
  assistantSending.value = true
  assistantStreaming.value = ''
  assistantError.value = ''
  const mode = assistantContextMode.value
  const blockId = mode === 'block' ? selectedBlock.value?.id ?? null : null
  const ac = new AbortController()
  assistantAbort = ac

  // Optimistic user bubble until SSE meta arrives (dedupe by id).
  const tempId = `temp-user-${Date.now()}`
  assistantMessages.value = [
    ...assistantMessages.value,
    {
      id: tempId,
      role: 'user',
      content,
      context_mode: mode,
      page_index: selectedBlock.value?.page_index ?? pageIndex.value,
      block_id: blockId,
      created_at: new Date().toISOString(),
    },
  ]

  try {
    await api.chatAssistantStream(
      props.id,
      {
        content,
        context_mode: mode,
        page_index: selectedBlock.value?.page_index ?? pageIndex.value,
        block_id: blockId,
      },
      {
        onUser: (msg) => {
          assistantMessages.value = assistantMessages.value.map((m) =>
            m.id === tempId ? msg : m,
          )
        },
        onDelta: (text) => {
          assistantStreaming.value += text
        },
        onDone: (msg) => {
          assistantStreaming.value = ''
          assistantSending.value = false
          assistantMessages.value = [...assistantMessages.value, msg]
        },
        onError: (detail) => {
          assistantStreaming.value = ''
          assistantSending.value = false
          assistantError.value = friendlyRailError(
            new Error(JSON.stringify({ detail })),
            'assistantErrConnect',
          )
        },
      },
      ac.signal,
    )
  } catch (err) {
    if ((err as { name?: string })?.name === 'AbortError') {
      const partial = assistantStreaming.value.trim()
      if (partial) {
        assistantMessages.value = [
          ...assistantMessages.value,
          {
            id: `local-partial-${Date.now()}`,
            role: 'assistant',
            content: `${partial}\n\n…`,
            context_mode: null,
            page_index: null,
            block_id: null,
            created_at: new Date().toISOString(),
          },
        ]
      }
    } else {
      if (assistantMessages.value.some((m) => m.id === tempId)) {
        assistantMessages.value = assistantMessages.value.filter((m) => m.id !== tempId)
      }
      assistantError.value = friendlyRailError(err, 'assistantErrConnect')
    }
  } finally {
    if (assistantAbort === ac) assistantAbort = null
    assistantSending.value = false
    assistantStreaming.value = ''
  }
}

async function clearAssistant() {
  if (!assistantMessages.value.length && !assistantSending.value) return
  stopAssistant()
  try {
    await api.clearAssistantMessages(props.id)
    assistantMessages.value = []
    assistantStreaming.value = ''
    assistantError.value = ''
  } catch (err) {
    assistantError.value = friendlyRailError(err, 'assistantErrConnect')
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
          :selected-block-id="activeSyncId"
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
            :blocks="currentBlocks"
            :highlights="pageHighlights"
            :selected-block-id="activeSyncId"
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
            :selected-block-id="activeSyncId"
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
        :selected-snippet="selectedSnippet"
        :busy="notesBusy"
        :error="notesError"
        @add="addNote"
        @remove="removeNote"
        @open="openNote"
      />
      <AssistantPanel
        v-show="railTab === 'assistant'"
        :messages="assistantMessages"
        :sending="assistantSending"
        :streaming-text="assistantStreaming"
        :error="assistantError"
        :context-mode="assistantContextMode"
        :selected-block-id="selectedBlock?.id ?? null"
        :selected-page="selectedBlock?.page_index ?? pageIndex"
        :selected-snippet="selectedSnippet"
        @send="sendAssistant"
        @stop="stopAssistant"
        @clear="clearAssistant"
        @update:context-mode="assistantContextMode = $event"
        @dismiss-error="assistantError = ''"
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
