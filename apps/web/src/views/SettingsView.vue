<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { KeyRound, Type, Check, PlugZap, Trash2, Pencil, X, Languages } from '@lucide/vue'
import { api, type ProviderItem, type ProviderPreset, type UiSettings } from '../api/client'
import { setLocale, t, type Locale } from '../i18n'

const settings = ref<UiSettings | null>(null)
const providers = ref<ProviderItem[]>([])
const presets = ref<ProviderPreset[]>([])
const message = ref('')
const messageOk = ref(true)
const testingId = ref<string | null>(null)
const editingId = ref<string | null>(null)
const formPanel = ref<HTMLElement | null>(null)
const resolvedPreview = ref('')
const testResults = reactive<Record<string, { ok: boolean; text: string }>>({})
const selectedPreset = ref('custom')

const form = reactive({
  name: 'Default',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  model: 'gpt-4o-mini',
  is_default: true,
  is_full_url: false,
})

const typography = reactive({
  font_family: 'Noto Serif SC, Source Han Serif SC, serif',
  font_size: 14,
  line_height: 1.65,
  view_mode: 'embedded' as 'embedded' | 'side',
  locale: 'zh' as Locale,
})

function resetForm() {
  editingId.value = null
  selectedPreset.value = 'custom'
  form.name = 'Default'
  form.base_url = 'https://api.openai.com/v1'
  form.api_key = ''
  form.model = 'gpt-4o-mini'
  form.is_default = true
  form.is_full_url = false
}

async function refreshPreview() {
  if (!form.base_url.trim()) {
    resolvedPreview.value = ''
    return
  }
  try {
    const res = await api.previewProviderUrl({
      base_url: form.base_url,
      is_full_url: form.is_full_url,
    })
    resolvedPreview.value = res.resolved_url
  } catch {
    resolvedPreview.value = ''
  }
}

watch(
  () => [form.base_url, form.is_full_url] as const,
  () => {
    void refreshPreview()
  },
)

function applyPreset(id: string) {
  selectedPreset.value = id
  const preset = presets.value.find((p) => p.id === id)
  if (!preset || id === 'custom') return
  form.name = preset.name
  form.base_url = preset.base_url
  form.model = preset.model
  form.is_full_url = false
}

async function load() {
  settings.value = await api.getSettings()
  providers.value = await api.listProviders()
  presets.value = await api.listProviderPresets()
  typography.font_family = settings.value.font_family
  typography.font_size = settings.value.font_size
  typography.line_height = settings.value.line_height
  typography.view_mode = settings.value.view_mode
  typography.locale = settings.value.locale === 'en' ? 'en' : 'zh'
  setLocale(typography.locale)
  await refreshPreview()
}

async function startEdit(p: ProviderItem) {
  editingId.value = p.id
  selectedPreset.value = 'custom'
  form.name = p.name
  form.base_url = p.base_url
  form.model = p.model
  form.is_default = p.is_default
  form.is_full_url = !!p.is_full_url
  form.api_key = ''
  message.value = t('settingsMsgEditing', { name: p.name })
  messageOk.value = true
  await nextTick()
  formPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  await refreshPreview()
}

function cancelEdit() {
  resetForm()
  message.value = ''
  void refreshPreview()
}

async function saveProvider() {
  try {
    const payload = { ...form }
    if (editingId.value) {
      await api.updateProvider(editingId.value, payload)
      message.value = t('settingsMsgUpdated')
      delete testResults[editingId.value]
    } else {
      await api.createProvider(payload)
      message.value = t('settingsMsgSaved')
    }
    messageOk.value = true
    resetForm()
    await load()
  } catch (err) {
    message.value = err instanceof Error ? err.message : String(err)
    messageOk.value = false
  }
}

async function saveTypography() {
  await api.putSettings({ ...typography })
  setLocale(typography.locale)
  message.value = t('settingsMsgPrefs')
  messageOk.value = true
  document.documentElement.style.setProperty('--font-trans', typography.font_family)
  document.documentElement.style.setProperty('--trans-size', `${typography.font_size}px`)
  document.documentElement.style.setProperty('--trans-leading', String(typography.line_height))
}

async function onLocaleChange() {
  setLocale(typography.locale)
  await api.putSettings({ locale: typography.locale })
  message.value = t('settingsMsgLocale')
  messageOk.value = true
}

async function removeProvider(id: string) {
  if (editingId.value === id) resetForm()
  await api.deleteProvider(id)
  delete testResults[id]
  await load()
}

async function testProvider(id: string) {
  testingId.value = id
  try {
    const result = await api.testProvider(id)
    const sample = result.sample ? ` · reply: “${result.sample}”` : ''
    const resolved = result.resolved_url ? ` · ${result.resolved_url}` : ''
    testResults[id] = {
      ok: result.ok,
      text: `${result.message} (${result.latency_ms} ms)${sample}${resolved}`,
    }
  } catch (err) {
    testResults[id] = {
      ok: false,
      text: err instanceof Error ? err.message : String(err),
    }
  } finally {
    testingId.value = null
  }
}

const hasProviders = computed(() => providers.value.length > 0)
const isEditing = computed(() => !!editingId.value)

onMounted(() => {
  load().catch((e) => {
    message.value = e instanceof Error ? e.message : String(e)
    messageOk.value = false
  })
})
</script>

<template>
  <div class="page page-narrow">
    <div class="page-header">
      <div>
        <p class="eyebrow">{{ t('settingsEyebrow') }}</p>
        <h1 class="hero-title">{{ t('settingsTitle') }}</h1>
        <p class="lead">{{ t('settingsLead') }}</p>
      </div>
    </div>

    <p v-if="message" class="alert" :class="{ ok: messageOk }">{{ message }}</p>

    <div class="settings-stack">
      <section class="panel">
        <h2 class="panel-title">
          <Languages :size="18" style="display: inline; vertical-align: -3px; margin-right: 6px" />
          {{ t('settingsUiLanguage') }}
        </h2>
        <p class="panel-desc">{{ t('settingsUiLanguageDesc') }}</p>
        <div class="field">
          <label>{{ t('settingsUiLanguage') }}</label>
          <select v-model="typography.locale" @change="onLocaleChange">
            <option value="zh">{{ t('settingsLangZh') }}</option>
            <option value="en">{{ t('settingsLangEn') }}</option>
          </select>
        </div>
      </section>

      <section ref="formPanel" class="panel">
        <h2 class="panel-title">
          <KeyRound :size="18" style="display: inline; vertical-align: -3px; margin-right: 6px" />
          {{ isEditing ? t('settingsEditProvider') : t('settingsAddProvider') }}
        </h2>
        <p class="panel-desc">{{ t('settingsProviderDesc') }}</p>

        <div class="field">
          <label>{{ t('settingsVendorPreset') }}</label>
          <select v-model="selectedPreset" @change="applyPreset(selectedPreset)">
            <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>{{ t('settingsProfileName') }}</label>
          <input v-model="form.name" />
        </div>
        <div class="field">
          <label>{{ t('settingsBaseUrl') }}</label>
          <input
            v-model="form.base_url"
            :placeholder="form.is_full_url ? 'https://host/custom/full/path' : 'https://apihub.agnes-ai.com/v1'"
          />
          <p class="muted" style="margin: 0.25rem 0 0; font-size: 0.78rem">
            {{ t('settingsBaseUrlHint') }}
          </p>
        </div>
        <div class="field">
          <label>{{ t('settingsResolvedUrl') }}</label>
          <input :value="resolvedPreview || '—'" readonly class="resolved-url" />
        </div>
        <div class="field">
          <label>{{ t('settingsApiKey') }}</label>
          <input
            v-model="form.api_key"
            type="password"
            :placeholder="isEditing ? t('settingsApiKeyKeep') : t('settingsApiKeyNew')"
          />
        </div>
        <div class="field">
          <label>{{ t('settingsModel') }}</label>
          <input v-model="form.model" />
        </div>
        <label class="check-row">
          <input v-model="form.is_default" type="checkbox" />
          {{ t('settingsUseDefault') }}
        </label>

        <details class="advanced">
          <summary>{{ t('settingsAdvanced') }}</summary>
          <label class="check-row" style="margin-top: 0.75rem">
            <input v-model="form.is_full_url" type="checkbox" />
            {{ t('settingsFullUrl') }}
          </label>
          <p class="muted" style="margin: 0; font-size: 0.78rem; line-height: 1.45">
            {{ t('settingsFullUrlHint') }}
          </p>
        </details>

        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.9rem">
          <button class="btn btn-primary" @click="saveProvider">
            <Check :size="16" />
            {{ isEditing ? t('settingsUpdateProvider') : t('settingsSaveProvider') }}
          </button>
          <button v-if="isEditing" class="btn" @click="cancelEdit">
            <X :size="16" />
            {{ t('settingsCancel') }}
          </button>
        </div>
      </section>

      <section class="panel">
        <h2 class="panel-title">{{ t('settingsSavedProviders') }}</h2>
        <p v-if="!hasProviders" class="panel-desc" style="margin-bottom: 0">{{ t('settingsNoneYet') }}</p>
        <div
          v-for="p in providers"
          :key="p.id"
          class="provider-row"
          :class="{ 'is-editing-row': editingId === p.id }"
        >
          <div style="min-width: 0; flex: 1">
            <strong>{{ p.name }}</strong>
            <div class="muted" style="font-size: 0.85rem; margin-top: 0.2rem; word-break: break-all">
              {{ p.model }} · {{ p.base_url }}
            </div>
            <div
              v-if="p.resolved_url"
              class="muted"
              style="font-size: 0.75rem; margin-top: 0.2rem; word-break: break-all"
            >
              → {{ p.resolved_url }}
            </div>
            <div style="margin-top: 0.35rem; display: flex; gap: 0.35rem; flex-wrap: wrap">
              <span v-if="p.is_default" class="badge ready">{{ t('settingsDefault') }}</span>
              <span v-if="p.has_api_key" class="badge">{{ t('settingsKeySet') }}</span>
              <span v-if="p.is_full_url" class="badge">{{ t('settingsFullUrlBadge') }}</span>
              <span v-if="editingId === p.id" class="badge">{{ t('settingsEditing') }}</span>
            </div>
            <p
              v-if="testResults[p.id]"
              class="alert"
              :class="{ ok: testResults[p.id].ok }"
              style="margin: 0.55rem 0 0; padding: 0.45rem 0.65rem; font-size: 0.82rem"
            >
              {{ testResults[p.id].text }}
            </p>
          </div>
          <div style="display: flex; gap: 0.35rem; flex-shrink: 0">
            <button class="btn" :title="t('settingsEdit')" @click="startEdit(p)">
              <Pencil :size="15" />
              {{ t('settingsEdit') }}
            </button>
            <button class="btn" :disabled="testingId === p.id" @click="testProvider(p.id)">
              <PlugZap :size="15" />
              {{ testingId === p.id ? t('settingsTesting') : t('settingsTest') }}
            </button>
            <button
              class="btn btn-ghost btn-danger btn-icon"
              :title="t('settingsDelete')"
              @click="removeProvider(p.id)"
            >
              <Trash2 :size="15" />
            </button>
          </div>
        </div>
      </section>

      <section class="panel">
        <h2 class="panel-title">
          <Type :size="18" style="display: inline; vertical-align: -3px; margin-right: 6px" />
          {{ t('settingsTypography') }}
        </h2>
        <p class="panel-desc">{{ t('settingsTypographyDesc') }}</p>
        <div class="field">
          <label>{{ t('settingsFontFamily') }}</label>
          <input v-model="typography.font_family" />
        </div>
        <div class="field">
          <label>{{ t('settingsFontSize') }}</label>
          <input v-model.number="typography.font_size" type="number" min="10" max="28" />
        </div>
        <div class="field">
          <label>{{ t('settingsLineHeight') }}</label>
          <input v-model.number="typography.line_height" type="number" min="1.2" max="2.4" step="0.1" />
        </div>
        <div class="field">
          <label>{{ t('settingsViewMode') }}</label>
          <select v-model="typography.view_mode">
            <option value="embedded">{{ t('settingsViewEmbedded') }}</option>
            <option value="side">{{ t('settingsViewSide') }}</option>
          </select>
        </div>
        <button class="btn btn-primary" @click="saveTypography">
          <Check :size="16" />
          {{ t('settingsSavePrefs') }}
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.provider-row.is-editing-row {
  background: var(--accent-soft, #e4eef5);
  margin: 0 -0.35rem;
  padding-left: 0.85rem;
  padding-right: 0.85rem;
  border-radius: 10px;
}
.resolved-url {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8rem;
  color: var(--muted, #6b7685);
  background: var(--surface-2, #f7f9fc) !important;
}
.advanced {
  margin-top: 0.35rem;
  border: 1px solid var(--line, #d5dde8);
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
  background: var(--surface-2, #f7f9fc);
}
.advanced summary {
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--ink-soft, #3a4452);
}
</style>
