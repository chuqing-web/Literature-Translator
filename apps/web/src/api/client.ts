const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return undefined as T
}

export type DocumentItem = {
  id: string
  title: string
  filename: string
  page_count: number
  status: string
  status_message: string
  created_at: string
  updated_at: string
}

export type BlockItem = {
  id: string
  page_index: number
  block_index: number
  text: string
  bbox_x0: number
  bbox_y0: number
  bbox_x1: number
  bbox_y1: number
  block_type: string
  font_size?: number
  page_width: number
  page_height: number
  translation: string | null
  translation_edited: boolean
  translation_status?: string | null
}

export type ProviderItem = {
  id: string
  name: string
  base_url: string
  model: string
  is_default: boolean
  has_api_key: boolean
  is_full_url?: boolean
  resolved_url?: string
}

export type ProviderPreset = {
  id: string
  name: string
  base_url: string
  model: string
}

export type UiSettings = {
  view_mode: 'embedded' | 'side'
  font_family: string
  font_size: number
  line_height: number
  active_provider_id: string | null
  locale: 'zh' | 'en'
}

export type NoteItem = {
  id: string
  document_id: string
  page_index: number
  block_id: string | null
  content: string
  color: string
  created_at: string
}

export type HighlightItem = {
  id: string
  document_id: string
  page_index: number
  block_id: string
  color: string
  created_at: string
}

export type TranslateJob = {
  id: string
  document_id: string
  status: string
  total: number
  done: number
  error: string
}

export type AssistantMessageItem = {
  id: string
  role: 'user' | 'assistant' | string
  content: string
  context_mode: string | null
  page_index: number | null
  block_id: string | null
  created_at: string
}

export type AssistantThreadResponse = {
  thread_id: string
  messages: AssistantMessageItem[]
}

export type AssistantChatResponse = {
  thread_id: string
  user_message: AssistantMessageItem
  assistant_message: AssistantMessageItem
}

export const api = {
  health: () => request<{ status: string; app: string }>('/api/health'),
  listDocuments: () => request<DocumentItem[]>('/api/documents'),
  uploadDocument: async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<DocumentItem>('/api/documents', { method: 'POST', body: fd })
  },
  getDocument: (id: string) => request<DocumentItem>(`/api/documents/${id}`),
  deleteDocument: (id: string) => request(`/api/documents/${id}`, { method: 'DELETE' }),
  reparseDocument: (id: string) =>
    request<DocumentItem>(`/api/documents/${id}/parse`, { method: 'POST' }),
  pdfUrl: (id: string) => `${API_BASE}/api/documents/${id}/file`,
  blockPreviewUrl: (docId: string, blockId: string, scale = 2) =>
    `${API_BASE}/api/documents/${docId}/blocks/${blockId}/preview.png?scale=${scale}`,
  pageBlocks: (id: string, page: number) =>
    request<BlockItem[]>(`/api/documents/${id}/pages/${page}/blocks`),
  allBlocks: (id: string) => request<BlockItem[]>(`/api/documents/${id}/blocks`),
  startTranslate: (id: string) =>
    request<{ job: TranslateJob }>(`/api/documents/${id}/translate`, { method: 'POST' }),
  jobStatus: (jobId: string) => request<TranslateJob>(`/api/translate/jobs/${jobId}`),
  updateTranslation: (blockId: string, text: string) =>
    request<BlockItem>(`/api/blocks/${blockId}/translation`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  getSettings: () => request<UiSettings>('/api/settings'),
  putSettings: (body: Partial<UiSettings>) =>
    request<UiSettings>('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  listProviders: () => request<ProviderItem[]>('/api/providers'),
  listProviderPresets: () => request<ProviderPreset[]>('/api/provider-presets'),
  previewProviderUrl: (body: { base_url: string; is_full_url: boolean }) =>
    request<{ resolved_url: string; mode: string }>('/api/providers/preview-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  createProvider: (body: {
    name: string
    base_url: string
    api_key: string
    model: string
    is_default: boolean
    is_full_url: boolean
  }) =>
    request<ProviderItem>('/api/providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  updateProvider: (
    id: string,
    body: {
      name: string
      base_url: string
      api_key: string
      model: string
      is_default: boolean
      is_full_url: boolean
    },
  ) =>
    request<ProviderItem>(`/api/providers/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteProvider: (id: string) => request(`/api/providers/${id}`, { method: 'DELETE' }),
  testProvider: (id: string) =>
    request<{
      ok: boolean
      message: string
      latency_ms: number
      sample?: string | null
      resolved_url?: string
    }>(`/api/providers/${id}/test`, { method: 'POST' }),
  listNotes: (id: string) => request<NoteItem[]>(`/api/documents/${id}/notes`),
  createNote: (
    id: string,
    body: { page_index: number; block_id?: string | null; content: string; color?: string },
  ) =>
    request<NoteItem>(`/api/documents/${id}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteNote: (docId: string, noteId: string) =>
    request(`/api/documents/${docId}/notes/${noteId}`, { method: 'DELETE' }),
  listHighlights: (id: string) => request<HighlightItem[]>(`/api/documents/${id}/highlights`),
  createHighlight: (id: string, body: { page_index: number; block_id: string; color?: string }) =>
    request<HighlightItem>(`/api/documents/${id}/highlights`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteHighlight: (docId: string, hlId: string) =>
    request(`/api/documents/${docId}/highlights/${hlId}`, { method: 'DELETE' }),
  exportDocxUrl: (id: string) => `${API_BASE}/api/documents/${id}/export.docx`,
  listAssistantMessages: (id: string) =>
    request<AssistantThreadResponse>(`/api/documents/${id}/assistant/messages`),
  clearAssistantMessages: (id: string) =>
    request<{ status: string }>(`/api/documents/${id}/assistant/messages`, { method: 'DELETE' }),
  chatAssistant: (
    id: string,
    body: {
      content: string
      context_mode?: 'auto' | 'full'
      page_index?: number
      block_id?: string | null
    },
  ) =>
    request<AssistantChatResponse>(`/api/documents/${id}/assistant/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
}
