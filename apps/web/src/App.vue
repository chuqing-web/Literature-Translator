<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { Library, Settings2, Languages } from '@lucide/vue'
import { api } from './api/client'
import { locale, setLocale, t, type Locale } from './i18n'
import type { MessageKey } from './i18n/messages'

const route = useRoute()
const isReader = computed(() => route.name === 'reader')
const switchLabel = computed(() =>
  locale.value === 'zh' ? t('langSwitchToEn') : t('langSwitchToZh'),
)

function tr(key: MessageKey) {
  return t(key)
}

async function toggleLocale() {
  const next: Locale = locale.value === 'zh' ? 'en' : 'zh'
  setLocale(next)
  try {
    await api.putSettings({ locale: next })
  } catch {
    /* local switch still applies */
  }
}

onMounted(async () => {
  try {
    const settings = await api.getSettings()
    if (settings.locale === 'zh' || settings.locale === 'en') {
      setLocale(settings.locale)
    }
  } catch {
    /* keep local default */
  }
})
</script>

<template>
  <div class="app-shell" :class="{ 'is-reader': isReader }">
    <header class="topbar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark" aria-hidden="true" />
        <template v-if="locale === 'zh'">
          {{ tr('brand') }}<em>{{ tr('brandEm') }}</em>
        </template>
        <template v-else>
          {{ tr('brand') }} <em>{{ tr('brandEm') }}</em>
        </template>
      </RouterLink>
      <nav class="nav-links">
        <button type="button" class="lang-toggle" :title="switchLabel" @click="toggleLocale">
          <Languages :size="15" :stroke-width="2" />
          {{ switchLabel }}
        </button>
        <RouterLink to="/">
          <Library :size="15" :stroke-width="2" />
          {{ tr('navLibrary') }}
        </RouterLink>
        <RouterLink to="/settings">
          <Settings2 :size="15" :stroke-width="2" />
          {{ tr('navSettings') }}
        </RouterLink>
      </nav>
    </header>
    <RouterView :key="locale" />
  </div>
</template>
