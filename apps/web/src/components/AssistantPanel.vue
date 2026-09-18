<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Bot, Eraser, FileText, Layers, SendHorizontal, Square, TextQuote, UserRound } from '@lucide/vue'
import type { AssistantMessageItem } from '../api/client'
import { t } from '../i18n'

export type AssistantContextMode = 'block' | 'page' | 'full'

const props = defineProps<{
  messages: AssistantMessageItem[]
  sending: boolean
  streamingText: string
  error: string
  contextMode: AssistantContextMode
  selectedBlockId: string | null
  selectedPage: number
  selectedSnippet: string | null
}>()

const emit = defineEmits<{
  send: [content: string]
  stop: []
  clear: []
  'update:contextMode': [value: AssistantContextMode]
  dismissError: []
}>()

const draft = ref('')
const listEl = ref<HTMLElement | null>(null)

const modes = computed(() => [
  {
    id: 'block' as const,
    label: t('assistantModeBlock'),
    icon: TextQuote,
    disabled: !props.selectedBlockId,
    title: props.selectedBlockId ? t('assistantModeBlockHint') : t('assistantModeBlockDisabled'),
  },
  {
    id: 'page' as const,
    label: t('assistantModePage'),
    icon: FileText,
    disabled: false,
    title: t('assistantModePageHint', { page: props.selectedPage + 1 }),
  },
  {
    id: 'full' as const,
    label: t('assistantModeFull'),
    icon: Layers,
    disabled: false,
    title: t('assistantModeFullHint'),
  },
])

const contextHint = computed(() => {
  if (props.contextMode === 'full') return t('assistantCtxFull')
  if (props.contextMode === 'block' && props.selectedBlockId) {
    return t('assistantCtxBlock', { page: props.selectedPage + 1 })
  }
  return t('assistantCtxPage', { page: props.selectedPage + 1 })
})

const showStreamBubble = computed(() => props.sending)

async function scrollToBottom() {
  await nextTick()
  const el = listEl.value
  if (el) el.scrollTop = el.scrollHeight
}

function submit() {
  const text = draft.value.trim()
  if (!text || props.sending) return
  draft.value = ''
  emit('send', text)
}

watch(
  () => props.messages.length,
  () => {
    void scrollToBottom()
  },
)

watch(
  () => [props.sending, props.streamingText] as const,
  () => {
    void scrollToBottom()
  },
)

watch(
  () => props.selectedBlockId,
  (id, prev) => {
    if (id && !prev && props.contextMode === 'page') {
      emit('update:contextMode', 'block')
    }
    if (!id && props.contextMode === 'block') {
      emit('update:contextMode', 'page')
    }
  },
)

function setMode(mode: AssistantContextMode) {
  if (mode === 'block' && !props.selectedBlockId) return
  emit('update:contextMode', mode)
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

function roleLabel(role: string): string {
  return role === 'user' ? t('assistantRoleUser') : t('assistantRoleAssistant')
}
</script>

<template>
  <aside class="assistant-panel">
    <header class="rail-panel-head">
      <div class="rail-panel-title">
        <Bot :size="17" color="var(--accent)" />
        <h3>{{ t('assistantTitle') }}</h3>
      </div>
      <button
        class="btn btn-ghost btn-icon"
        type="button"
        :title="t('assistantClear')"
        :disabled="(!messages.length && !sending) || sending"
        @click="emit('clear')"
      >
        <Eraser :size="14" />
      </button>
    </header>

    <div class="assistant-context">
      <div class="context-mode-row" role="radiogroup" :aria-label="t('assistantContextScope')">
        <button
          v-for="mode in modes"
          :key="mode.id"
          type="button"
          role="radio"
          class="context-chip"
          :class="{ active: contextMode === mode.id }"
          :aria-checked="contextMode === mode.id"
          :disabled="mode.disabled || sending"
          :title="mode.title"
          @click="setMode(mode.id)"
        >
          <component :is="mode.icon" :size="13" />
          {{ mode.label }}
        </button>
      </div>
      <p class="context-live muted">{{ contextHint }}</p>
      <p v-if="contextMode === 'block' && selectedSnippet" class="anchor-snippet">{{ selectedSnippet }}</p>
    </div>

    <div ref="listEl" class="assistant-messages cline-thread">
      <div v-if="!messages.length && !sending" class="assistant-empty-card">
        <p class="muted">{{ t('assistantEmpty') }}</p>
        <ul class="assistant-tips">
          <li>{{ t('assistantTip1') }}</li>
          <li>{{ t('assistantTip2') }}</li>
          <li>{{ t('assistantTip3') }}</li>
        </ul>
      </div>

      <div
        v-for="msg in messages"
        :key="msg.id"
        class="chat-row"
        :class="msg.role === 'user' ? 'is-user' : 'is-assistant'"
      >
        <div class="chat-avatar" aria-hidden="true">
          <UserRound v-if="msg.role === 'user'" :size="14" />
          <Bot v-else :size="14" />
        </div>
        <div class="chat-col">
          <div class="chat-role">{{ roleLabel(msg.role) }}</div>
          <div v-if="contextLabel(msg)" class="chat-meta">{{ contextLabel(msg) }}</div>
          <div class="chat-bubble">{{ msg.content }}</div>
        </div>
      </div>

      <div v-if="showStreamBubble" class="chat-row is-assistant is-streaming">
        <div class="chat-avatar" aria-hidden="true">
          <Bot :size="14" />
        </div>
        <div class="chat-col">
          <div class="chat-role">{{ t('assistantRoleAssistant') }}</div>
          <div class="chat-bubble">
            <span v-if="streamingText">{{ streamingText }}</span>
            <span v-else class="chat-thinking">{{ t('assistantThinking') }}</span>
            <span class="chat-caret" aria-hidden="true" />
          </div>
        </div>
      </div>
    </div>

    <div v-if="error" class="alert rail-error assistant-error">
      <span>{{ error }}</span>
      <button type="button" class="btn btn-ghost" style="font-size: 0.75rem" @click="emit('dismissError')">
        {{ t('assistantDismissError') }}
      </button>
    </div>

    <div class="assistant-composer">
      <textarea
        v-model="draft"
        rows="3"
        :placeholder="t('assistantPlaceholder')"
        :disabled="sending"
        @keydown="onKeydown"
      />
      <div class="composer-actions">
        <span class="composer-hint">{{ t('assistantShortcut') }}</span>
        <button
          v-if="sending"
          class="btn btn-danger-ghost"
          type="button"
          @click="emit('stop')"
        >
          <Square :size="13" />
          {{ t('assistantStop') }}
        </button>
        <button
          v-else
          class="btn btn-primary"
          type="button"
          :disabled="!draft.trim()"
          @click="submit"
        >
          <SendHorizontal :size="15" />
          {{ t('assistantSend') }}
        </button>
      </div>
    </div>
  </aside>
</template>
