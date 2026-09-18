<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Link2, MapPin, StickyNote, Trash2 } from '@lucide/vue'
import type { NoteItem } from '../api/client'
import { t } from '../i18n'

const props = defineProps<{
  notes: NoteItem[]
  selectedBlockId: string | null
  selectedPage: number
  selectedSnippet: string | null
  busy?: boolean
  error?: string
}>()

const emit = defineEmits<{
  add: [content: string]
  remove: [id: string]
  open: [note: NoteItem]
}>()

const draft = ref('')
const pendingAdd = ref(false)

const anchored = computed(() => !!props.selectedBlockId)

const sortedNotes = computed(() =>
  [...props.notes].sort((a, b) => {
    if (a.page_index !== b.page_index) return a.page_index - b.page_index
    return b.created_at.localeCompare(a.created_at)
  }),
)

watch(
  () => props.notes.length,
  (len, prev) => {
    if (pendingAdd.value && len > (prev ?? 0)) {
      draft.value = ''
      pendingAdd.value = false
    }
  },
)

watch(
  () => props.busy,
  (busy) => {
    if (!busy && pendingAdd.value && props.error) pendingAdd.value = false
  },
)

function submit() {
  if (!draft.value.trim() || props.busy) return
  pendingAdd.value = true
  emit('add', draft.value.trim())
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    submit()
  }
}

function noteLabel(note: NoteItem): string {
  if (note.block_id) return t('notesAnchorBlock', { page: note.page_index + 1 })
  return t('notesPage', { page: note.page_index + 1 })
}
</script>

<template>
  <aside class="notes-panel">
    <header class="rail-panel-head">
      <div class="rail-panel-title">
        <StickyNote :size="17" color="var(--accent)" />
        <h3>{{ t('notesTitle') }}</h3>
      </div>
      <span class="rail-count" v-if="notes.length">{{ notes.length }}</span>
    </header>

    <div class="anchor-card" :class="{ 'is-anchored': anchored }">
      <div class="anchor-card-row">
        <component :is="anchored ? Link2 : MapPin" :size="14" />
        <span>{{
          anchored ? t('notesAnchored', { page: selectedPage + 1 }) : t('notesPageOnly', { page: selectedPage + 1 })
        }}</span>
      </div>
      <p v-if="anchored && selectedSnippet" class="anchor-snippet">{{ selectedSnippet }}</p>
      <p v-else class="anchor-hint">{{ anchored ? t('notesAnchoredHint') : t('notesSelect') }}</p>
    </div>

    <div class="field notes-composer">
      <textarea
        v-model="draft"
        rows="3"
        :placeholder="t('notesPlaceholder')"
        :disabled="busy"
        @keydown="onKeydown"
      />
      <div class="composer-actions">
        <span class="composer-hint">{{ t('notesShortcut') }}</span>
        <button class="btn btn-primary" type="button" :disabled="!draft.trim() || busy" @click="submit">
          {{ busy ? t('notesAdding') : t('notesAdd') }}
        </button>
      </div>
    </div>

    <p v-if="error" class="alert rail-error">{{ error }}</p>

    <div class="notes-list">
      <button
        v-for="note in sortedNotes"
        :key="note.id"
        type="button"
        class="note-item"
        :class="{ 'has-block': !!note.block_id }"
        @click="emit('open', note)"
      >
        <div class="note-meta">
          <span class="note-anchor-label">
            <component :is="note.block_id ? Link2 : MapPin" :size="12" />
            {{ noteLabel(note) }}
          </span>
          <button
            class="btn btn-ghost btn-icon"
            type="button"
            :title="t('notesDelete')"
            :disabled="busy"
            @click.stop="emit('remove', note.id)"
          >
            <Trash2 :size="14" />
          </button>
        </div>
        <div class="note-body">{{ note.content }}</div>
        <span class="note-open-hint">{{ t('notesOpenHint') }}</span>
      </button>
      <p v-if="!notes.length" class="muted notes-empty">{{ t('notesEmpty') }}</p>
    </div>
  </aside>
</template>
