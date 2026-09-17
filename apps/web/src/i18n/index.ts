import { computed, ref } from 'vue'
import { messages, type Locale, type MessageKey } from './messages'

export type { Locale, MessageKey }

const STORAGE_KEY = 'lt-ui-locale'

function readStored(): Locale | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'zh' || v === 'en') return v
  } catch {
    /* ignore */
  }
  return null
}

/** Default Chinese UI; fall back to stored / browser hint. */
function initialLocale(): Locale {
  const stored = readStored()
  if (stored) return stored
  const nav = typeof navigator !== 'undefined' ? navigator.language.toLowerCase() : 'zh'
  return nav.startsWith('zh') ? 'zh' : 'en'
}

export const locale = ref<Locale>(initialLocale())

export function t(key: MessageKey, params?: Record<string, string | number>): string {
  const table = messages[locale.value] || messages.zh
  let text: string = table[key] || messages.en[key] || String(key)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replaceAll(`{${k}}`, String(v))
    }
  }
  return text
}

export function setLocale(next: Locale) {
  locale.value = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* ignore */
  }
  if (typeof document !== 'undefined') {
    document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en'
    document.title = next === 'zh' ? '文献翻译器' : 'Literature Translator'
  }
}

export function useI18n() {
  return {
    locale: computed(() => locale.value),
    t,
    setLocale,
  }
}

// Apply document lang on load
setLocale(locale.value)
