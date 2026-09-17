<script setup lang="ts">
import { ref } from 'vue'
import { StickyNote, Trash2 } from '@lucide/vue'
import type { NoteItem } from '../api/client'
import { t } from '../i18n'

defineProps<{
  notes: NoteItem[]
  selectedBlockId: string | null
  selectedPage: number
}>()

const emit = defineEmits<{
  add: [content: string]
  remove: [id: string]
}>()

const draft = ref('')

function submit() {
  if (!draft.value.trim()) return
  emit('add', draft.value.trim())
  draft.value = ''
}
</script>

<template>
  <aside class="notes-panel">
    <div style="display: flex; align-items: center; gap: 0.45rem">
      <StickyNote :size="18" color="var(--accent)" />
      <h3 style="margin: 0">{{ t('notesTitle') }}</h3>
    </div>
    <p class="muted" style="margin: 0; font-size: 0.82rem; line-height: 1.45">
      {{
        selectedBlockId
          ? t('notesAnchored', { page: selectedPage + 1 })
          : t('notesSelect')
      }}
    </p>
    <div class="field" style="margin-bottom: 0.5rem">
      <textarea v-model="draft" rows="4" :placeholder="t('notesPlaceholder')" />
    </div>
    <button class="btn btn-primary" :disabled="!draft.trim()" @click="submit">{{ t('notesAdd') }}</button>

    <div style="margin-top: 0.5rem; display: grid; gap: 0.65rem">
      <div v-for="note in notes" :key="note.id" class="note-item">
        <div class="note-meta">
          <span>{{ t('notesPage', { page: note.page_index + 1 }) }}</span>
          <button
            class="btn btn-ghost btn-icon"
            :title="t('notesDelete')"
            @click="emit('remove', note.id)"
          >
            <Trash2 :size="14" />
          </button>
        </div>
        <div style="font-size: 0.92rem; line-height: 1.45">{{ note.content }}</div>
      </div>
      <p v-if="!notes.length" class="muted" style="font-size: 0.85rem; margin: 0.5rem 0 0">
        {{ t('notesEmpty') }}
      </p>
    </div>
  </aside>
</template>
