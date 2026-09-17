<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Bot, Eraser, SendHorizontal } from '@lucide/vue'
import type { AssistantMessageItem } from '../api/client'
import { t } from '../i18n'

const props = defineProps<{
  messages: AssistantMessageItem[]
  sending: boolean
  error: string
  useFullDoc: boolean
  selectedBlockId: string | null
  selectedPage: number
}>()

const emit = defineEmits<{
  send: [content: string]
  clear: []
  'update:useFullDoc': [value: boolean]
}>()

const draft = ref('')
const listEl = ref<HTMLElement | null>(null)

const contextHint = computed(() => {
  if (props.useFullDoc) return t('assistantCtxFull')
  if (props.selectedBlockId) return t('assistantCtxBlock', { page: props.selectedPage + 1 })
  return t('assistantCtxPage', { page: props.selectedPage + 1 })
})

async function scrollToBottom() {
  await nextTick()
  const el = listEl.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(
  () => props.messages.length,
  () => {
    void scrollToBottom()
  },
)

function submit() {
  const text = draft.value.trim()
  if (!text || props.sending) return
  emit('send', text)
  draft.value = ''
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}

function contextLabel(msg: AssistantMessageItem): string | null {
  if (msg.role !== 'user' || !msg.context_mode) return null
  if (msg.context_mode === 'full') return t('assistantCtxFull')
  if (msg.context_mode === 'block') {
    const page = (msg.page_index ?? 0) + 1
    return t('assistantCtxBlock', { page })
  }
  const page = (msg.page_index ?? 0) + 1
  return t('assistantCtxPage', { page })
}
</script>

<template>
  <aside class="assistant-panel">
    <div class="assistant-head">
      <div style="display: flex; align-items: center; gap: 0.45rem; min-width: 0">
        <Bot :size="18" color="var(--accent)" />
        <h3 style="margin: 0">{{ t('assistantTitle') }}</h3>
      </div>
      <button
        class="btn btn-ghost btn-icon"
        type="button"
        :title="t('assistantClear')"
        :disabled="!messages.length || sending"
        @click="emit('clear')"
      >
        <Eraser :size="14" />
      </button>
    </div>

    <div class="assistant-context">
      <span class="muted" style="font-size: 0.78rem; line-height: 1.35">{{ contextHint }}</span>
      <label class="assistant-full-toggle">
        <input
          type="checkbox"
          :checked="useFullDoc"
          :disabled="sending"
          @change="emit('update:useFullDoc', ($event.target as HTMLInputElement).checked)"
        />
        {{ t('assistantUseFull') }}
      </label>
    </div>

    <div ref="listEl" class="assistant-messages">
      <p v-if="!messages.length" class="muted assistant-empty">{{ t('assistantEmpty') }}</p>
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="assistant-bubble"
        :class="msg.role === 'user' ? 'is-user' : 'is-assistant'"
      >
        <div v-if="contextLabel(msg)" class="assistant-msg-meta">{{ contextLabel(msg) }}</div>
        <div class="assistant-msg-body">{{ msg.content }}</div>
      </div>
      <div v-if="sending" class="assistant-bubble is-assistant is-pending">
        <div class="assistant-msg-body">{{ t('assistantThinking') }}</div>
      </div>
    </div>

    <p v-if="error" class="alert" style="margin: 0; font-size: 0.8rem; padding: 0.5rem 0.65rem">
      {{ error }}
    </p>

    <div class="assistant-composer">
      <textarea
        v-model="draft"
        rows="3"
        :placeholder="t('assistantPlaceholder')"
        :disabled="sending"
        @keydown="onKeydown"
      />
      <button class="btn btn-primary" type="button" :disabled="!draft.trim() || sending" @click="submit">
        <SendHorizontal :size="15" />
        {{ sending ? t('assistantSending') : t('assistantSend') }}
      </button>
    </div>
  </aside>
</template>
