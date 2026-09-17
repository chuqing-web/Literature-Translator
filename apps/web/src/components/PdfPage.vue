<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as pdfjs from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import type { BlockItem, HighlightItem } from '../api/client'
import { t } from '../i18n'

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker

const props = defineProps<{
  pdfUrl: string
  pageIndex: number
  scale?: number
  forcedWidth?: number
  forcedHeight?: number
  blocks: BlockItem[]
  highlights: HighlightItem[]
  mode: 'embedded' | 'side'
  side: 'source' | 'translation'
}>()

const emit = defineEmits<{
  rendered: [payload: { width: number; height: number }]
  selectBlock: [block: BlockItem]
  saveTranslation: [payload: { blockId: string; text: string }]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const wrapRef = ref<HTMLDivElement | null>(null)
const cssWidth = ref(0)
const cssHeight = ref(0)
const renderError = ref('')
const loading = ref(false)

let pdfDoc: PDFDocumentProxy | null = null
let loadedUrl = ''
let renderTask: RenderTask | null = null
let renderToken = 0
let lastParentWidth = 0
let resizeTimer: ReturnType<typeof setTimeout> | null = null
let resizeObserver: ResizeObserver | null = null

type TextLevel = 'title' | 'heading' | 'body' | 'caption' | 'meta'

/** Fixed hierarchy sizes — same level shares one size across the whole paper. */
const LEVEL_SIZE: Record<TextLevel, number> = {
  title: 17,
  heading: 13.5,
  body: 11.5,
  caption: 10.5,
  meta: 10.5,
}

const LEVEL_LINE: Record<TextLevel, number> = {
  title: 1.3,
  heading: 1.35,
  body: 1.55,
  caption: 1.5,
  meta: 1.45,
}

type PackedBox = {
  left: number
  top: number
  width: number
  height: number
  eraseTop: number
  eraseHeight: number
  level: TextLevel
  fontPx: number
  lineHeight: number
  centered: boolean
}

/** Actual textarea scrollHeight overrides (px) after paint — fixes canvas under-measure. */
const heightOverrides = ref<Record<string, number>>({})
let fitTimer: ReturnType<typeof setTimeout> | null = null

/** True when the PDF bbox is horizontally centered on the page (titles, authors). */
function isCenteredBlock(block: BlockItem): boolean {
  const pageW = block.page_width || 0
  if (pageW < 50) return false
  const left = block.bbox_x0
  const right = pageW - block.bbox_x1
  const cx = (block.bbox_x0 + block.bbox_x1) / 2
  const mid = pageW / 2
  const marginBalance = Math.abs(left - right)
  const centerDrift = Math.abs(cx - mid)
  if (marginBalance > Math.max(22, pageW * 0.05)) return false
  if (centerDrift > Math.max(16, pageW * 0.04)) return false
  return true
}

/** Longest line width in CSS px for the overlay font. */
function measureTextWidthPx(text: string, fontPx: number): number {
  const raw = text.trim() || '…'
  if (typeof document === 'undefined') return Math.ceil(raw.length * fontPx * 0.95)
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) return Math.ceil(raw.length * fontPx * 0.95)
  ctx.font = `${fontPx}px var(--font-trans), "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif`
  // canvas ignores CSS vars — use concrete stack
  ctx.font = `${fontPx}px "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif`
  let max = 0
  for (const line of raw.split(/\n+/)) {
    max = Math.max(max, ctx.measureText(line).width)
  }
  return Math.ceil(max)
}

function safeCleanupDoc(doc: PDFDocumentProxy | null) {
  if (!doc) return
  try {
    const anyDoc = doc as { destroy?: () => unknown; cleanup?: () => unknown }
    if (typeof anyDoc.destroy === 'function') void anyDoc.destroy()
    else if (typeof anyDoc.cleanup === 'function') anyDoc.cleanup()
  } catch {
    /* ignore */
  }
}

async function ensurePdf(): Promise<PDFDocumentProxy> {
  if (pdfDoc && loadedUrl === props.pdfUrl) return pdfDoc
  safeCleanupDoc(pdfDoc)
  pdfDoc = null
  loadedUrl = props.pdfUrl

  const res = await fetch(props.pdfUrl)
  if (!res.ok) throw new Error(t('pdfLoadFailed', { status: res.status }))
  const data = new Uint8Array(await res.arrayBuffer())
  pdfDoc = await pdfjs.getDocument({ data, useSystemFonts: true }).promise
  return pdfDoc
}

/** Only overlay real body/caption text — keep figures & formulas visible on the PDF. */
function isOverlayBlock(block: BlockItem): boolean {
  if (
    block.block_type === 'formula_skip' ||
    block.block_type === 'skip' ||
    block.block_type === 'placeholder_figure' ||
    block.block_type === 'placeholder_table'
  ) {
    return false
  }
  const w = block.bbox_x1 - block.bbox_x0
  const h = block.bbox_y1 - block.bbox_y0
  if (w < 14 || h < 8) return false
  if (h > Math.max(48, w * 2.4) && w < 48) return false
  // Ornamental drop-cap letter extracted alone
  const compact = (block.text || '').replace(/\s+/g, '')
  if (/^[A-Za-z]$/.test(compact)) return false
  return (
    block.block_type === 'text' ||
    block.block_type === 'caption' ||
    block.block_type === 'heading' ||
    block.block_type === 'title' ||
    block.block_type === 'meta'
  )
}

const overlayBlocks = computed(() => props.blocks.filter(isOverlayBlock))

function textLevel(block: BlockItem): TextLevel {
  if (block.block_type === 'caption') return 'caption'
  if (block.block_type === 'title') return 'title'
  if (block.block_type === 'heading') return 'heading'
  if (block.block_type === 'meta') return 'meta'
  const text = (block.text || '').replace(/\s+/g, ' ').trim()
  const h = block.bbox_y1 - block.bbox_y0
  const w = block.bbox_x1 - block.bbox_x0
  if (/^\d+(\.\d+)*\s+\S/.test(text) && text.length < 90 && h < 42) return 'heading'
  if (block.page_index === 0 && block.block_index === 0 && h < 48 && text.length < 180) {
    return 'title'
  }
  if (
    block.page_index === 0 &&
    block.block_index > 0 &&
    block.block_index <= 5 &&
    h < 55 &&
    w / Math.max(h, 1) > 2.2 &&
    text.length < 500
  ) {
    return 'meta'
  }
  return 'body'
}

function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxW: number): number {
  const paragraphs = text.split(/\n+/)
  let lines = 0
  for (const para of paragraphs) {
    if (!para) {
      lines += 1
      continue
    }
    let line = ''
    for (const ch of para) {
      const trial = line + ch
      if (ctx.measureText(trial).width > maxW && line) {
        lines += 1
        line = ch
      } else {
        line = trial
      }
    }
    if (line) lines += 1
  }
  return Math.max(1, lines)
}

/** Measure with a real DOM node so wrap/line-height match the textarea. */
function measureContentHeight(text: string, boxW: number, fontPx: number, lineHeight: number): number {
  const raw = text.trim() || '…'
  const oneLine = fontPx * lineHeight
  if (typeof document === 'undefined') {
    return Math.ceil(raw.length / Math.max(8, boxW / fontPx)) * oneLine + 8
  }

  const probe = document.createElement('div')
  probe.setAttribute('aria-hidden', 'true')
  probe.style.cssText = [
    'position:absolute',
    'left:-99999px',
    'top:0',
    `width:${Math.max(12, boxW)}px`,
    'visibility:hidden',
    'pointer-events:none',
    'white-space:pre-wrap',
    'word-break:break-word',
    'overflow-wrap:anywhere',
    `font:${fontPx}px var(--font-trans), "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif`,
    `line-height:${lineHeight}`,
    'padding:0',
    'margin:0',
    'border:none',
  ].join(';')
  probe.textContent = raw
  document.body.appendChild(probe)
  const h = probe.scrollHeight
  probe.remove()

  // Safety: canvas line-count as lower bound if font not loaded yet (probe may be short)
  let canvasLines = 1
  try {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (ctx) {
      ctx.font = `${fontPx}px "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif`
      canvasLines = wrapLines(ctx, raw, Math.max(12, boxW - 4))
    }
  } catch {
    /* ignore */
  }
  const fromCanvas = Math.ceil(canvasLines * oneLine)
  // Extra room for descenders / subpixel rounding / serif overhang
  return Math.max(h, fromCanvas, oneLine) + Math.ceil(fontPx * 0.45) + 6
}

/**
 * Headings/titles must stay one visual line. Model output often inserts a newline
 * after the section number ("2\\n相关工作"), which doubles height inside a short
 * PDF bbox and gets clipped to a black smear by overflow:hidden.
 */
function layoutText(block: BlockItem, raw: string): string {
  let t = (raw || '').trim()
  if (!t) return t
  const level = textLevel(block)
  if (level === 'heading' || level === 'title') {
    t = t.replace(/\s+/g, ' ')
    // Drop-cap left on the heading ("一、引言 B" / "I. INTRODUCTION B")
    t = t.replace(/\s+[A-Za-z]$/u, '').trim()
  }
  // Bare ornamental initial — never show as its own overlay
  if (/^[A-Za-z]$/u.test(t)) return ''
  return t
}

/**
 * Pack translation boxes: hide English with full-bbox erase masks, place Chinese
 * at measured content height (never clip mid-glyph). Packing is per-column so
 * two-column pages stay independent; later boxes never overlap earlier ones.
 */
const packedLayout = computed(() => {
  const map = new Map<string, PackedBox>()
  // Touch overrides so fit pass re-triggers packing
  const overrides = heightOverrides.value
  if (!cssWidth.value || !cssHeight.value || !overlayBlocks.value.length) return map

  const pageW = overlayBlocks.value[0].page_width
  const pageH = overlayBlocks.value[0].page_height
  if (!pageW || !pageH) return map

  const sx = cssWidth.value / pageW
  const sy = cssHeight.value / pageH
  const pad = props.mode === 'side' && props.side === 'translation' ? 1.25 : 0
  const midX = pageW / 2
  const sorted = [...overlayBlocks.value].sort(
    (a, b) => a.bbox_y0 - b.bbox_y0 || a.bbox_x0 - b.bbox_x0,
  )

  type ColState = {
    prevBottom: number
    prevSrcBottom: number
    prevWasBody: boolean
    prevWasHeading: boolean
  }
  const cols: Record<'full' | 'left' | 'right', ColState> = {
    full: { prevBottom: 0, prevSrcBottom: -1e9, prevWasBody: false, prevWasHeading: false },
    left: { prevBottom: 0, prevSrcBottom: -1e9, prevWasBody: false, prevWasHeading: false },
    right: { prevBottom: 0, prevSrcBottom: -1e9, prevWasBody: false, prevWasHeading: false },
  }

  function columnOf(block: BlockItem): 'full' | 'left' | 'right' {
    const cx = (block.bbox_x0 + block.bbox_x1) / 2
    const w = block.bbox_x1 - block.bbox_x0
    if (w >= pageW * 0.55) return 'full'
    return cx < midX ? 'left' : 'right'
  }

  for (const block of sorted) {
    const level = textLevel(block)
    const centered = isCenteredBlock(block)
    const srcPt = block.font_size || 0
    const fontPx =
      srcPt > 0
        ? Math.round(Math.min(22, Math.max(9, srcPt * sy)) * 10) / 10
        : LEVEL_SIZE[level]
    const lineHeight = LEVEL_LINE[level]
    let left = block.bbox_x0 * sx - pad
    let width = Math.max(24, (block.bbox_x1 - block.bbox_x0) * sx + pad * 2)

    const text = layoutText(block, block.translation || '')
    const fallback = layoutText(block, block.text || '…')
    const display = text || fallback

    if (centered) {
      // Centered titles/authors: use a wide page band so Chinese isn't clipped by a tight English bbox
      const margin = Math.max(14, cssWidth.value * 0.035)
      const maxW = Math.max(48, cssWidth.value - margin * 2)
      const natural = measureTextWidthPx(display, fontPx) + 12
      // Prefer wrapping inside ~90% page width rather than overflowing a narrow line box
      width = Math.min(maxW, Math.max(width, Math.min(natural, cssWidth.value * 0.92)))
      left = (cssWidth.value - width) / 2
    } else if (level === 'heading' || level === 'title') {
      width = Math.max(width, Math.min(cssWidth.value * 0.48, fontPx * 12))
    }

    const measureW = width
    const srcTop = block.bbox_y0 * sy - pad
    const srcHeight = Math.max(12, (block.bbox_y1 - block.bbox_y0) * sy + pad * 2)
    const srcBottom = srcTop + srcHeight
    const col = columnOf(block)
    const state = cols[col]
    const srcGap = srcTop - state.prevSrcBottom

    const measured = measureContentHeight(display, measureW, fontPx, lineHeight)
    const oneLine = fontPx * lineHeight + 6
    let contentH = Math.max(measured, oneLine, overrides[block.id] || 0)
    // Non-centered short headings stay compact; centered titles may wrap freely
    if ((level === 'heading' || level === 'title') && !centered) {
      contentH = Math.max(oneLine, Math.min(contentH, oneLine * 1.25))
      if (overrides[block.id]) contentH = Math.max(contentH, overrides[block.id])
    }

    let top = srcTop
    if (state.prevSrcBottom > -1e8) {
      if (srcGap > 42) {
        top = srcTop
      } else if (level === 'heading' || level === 'title') {
        top = srcTop
      } else if (state.prevWasBody && (level === 'body' || level === 'caption') && srcGap <= 22) {
        top = Math.min(srcTop, state.prevBottom + 6)
      } else {
        top = srcTop
      }
      top = Math.max(top, state.prevBottom + (state.prevWasHeading ? 6 : 4))
    }

    const boxH = contentH
    map.set(block.id, {
      left,
      top,
      width,
      height: boxH,
      eraseTop: Math.min(srcTop, top),
      eraseHeight: Math.max(srcHeight + Math.max(0, srcTop - top), boxH + Math.max(0, top - srcTop)),
      level,
      fontPx,
      lineHeight,
      centered,
    })

    const next: ColState = {
      prevBottom: top + boxH,
      prevSrcBottom: Math.max(srcBottom, top + boxH),
      prevWasBody: level === 'body' || level === 'caption' || level === 'meta',
      prevWasHeading: level === 'heading' || level === 'title',
    }
    cols[col] = next
    if (col === 'full') {
      cols.left = { ...next }
      cols.right = { ...next }
    }
  }

  return map
})

/** Grow boxes to real textarea scroll size, then packing recomputes via overrides. */
async function fitOverlayHeights() {
  if (props.mode !== 'side' || props.side !== 'translation') return
  await nextTick()
  const root = wrapRef.value
  if (!root) return
  const next: Record<string, number> = { ...heightOverrides.value }
  let changed = false
  for (const node of root.querySelectorAll<HTMLElement>('.trans-block[data-block-id]')) {
    const id = node.dataset.blockId
    if (!id) continue
    const ta = node.querySelector('textarea')
    if (!ta) continue
    const prev = ta.style.height
    ta.style.height = '0px'
    const needH = Math.ceil(ta.scrollHeight) + 4
    ta.style.height = prev
    const cur = packedLayout.value.get(id)?.height || 0
    if (needH > cur + 1 && needH > (next[id] || 0) + 0.5) {
      next[id] = needH
      changed = true
    }
  }
  if (changed) heightOverrides.value = next
}
async function renderPage() {
  const token = ++renderToken
  renderError.value = ''
  loading.value = true

  try {
    await nextTick()
    const canvas = canvasRef.value
    if (!canvas) {
      loading.value = false
      return
    }

    if (renderTask) {
      try {
        renderTask.cancel()
      } catch {
        /* ignore */
      }
      renderTask = null
    }

    const pdf = await ensurePdf()
    if (token !== renderToken) return

    const page = await pdf.getPage(props.pageIndex + 1)
    const base = page.getViewport({ scale: 1 })
    const parentW = wrapRef.value?.parentElement?.clientWidth || 720
    lastParentWidth = parentW
    let targetWidth = Math.min(860, Math.max(320, parentW - 12))
    if (props.forcedWidth) targetWidth = props.forcedWidth
    const scale =
      props.scale ||
      (props.forcedWidth ? props.forcedWidth / base.width : targetWidth / base.width)
    const viewport = page.getViewport({ scale })
    const outputScale = Math.min(window.devicePixelRatio || 1, 2)

    const cssW = Math.floor(viewport.width)
    const cssH = Math.floor(viewport.height)
    canvas.width = Math.floor(cssW * outputScale)
    canvas.height = Math.floor(cssH * outputScale)
    canvas.style.width = `${cssW}px`
    canvas.style.height = `${cssH}px`
    cssWidth.value = cssW
    cssHeight.value = cssH

    const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('2D canvas unavailable')
    renderTask = page.render({ canvasContext: ctx, canvas, viewport, transform })
    await renderTask.promise
    renderTask = null

    if (token !== renderToken) return
    emit('rendered', { width: cssW, height: cssH })
    if (fitTimer) clearTimeout(fitTimer)
    fitTimer = setTimeout(() => {
      const fontsReady =
        typeof document !== 'undefined' && document.fonts?.ready
          ? document.fonts.ready
          : Promise.resolve()
      void fontsReady.then(() => fitOverlayHeights()).catch(() => void fitOverlayHeights())
    }, 50)
  } catch (err) {
    if ((err as { name?: string })?.name === 'RenderingCancelledException') return
    renderError.value = err instanceof Error ? err.message : String(err)
    console.error('[PdfPage] render failed', err)
  } finally {
    if (token === renderToken) loading.value = false
  }
}

function eraseStyle(block: BlockItem) {
  const box = packedLayout.value.get(block.id)
  if (!box || props.mode !== 'side' || props.side !== 'translation') {
    return { display: 'none' }
  }
  if (!block.translation) return { display: 'none' }
  return {
    left: `${box.left}px`,
    top: `${box.eraseTop}px`,
    width: `${box.width}px`,
    height: `${box.eraseHeight}px`,
  }
}

function blockStyle(block: BlockItem) {
  if (!cssWidth.value || !cssHeight.value || !block.page_width || !block.page_height) {
    return { display: 'none' }
  }

  if (props.mode === 'embedded' && props.side === 'source') {
    const sx = cssWidth.value / block.page_width
    const sy = cssHeight.value / block.page_height
    const level = textLevel(block)
    const fontPx = LEVEL_SIZE[level]
    const centered = isCenteredBlock(block)
    return {
      left: `${block.bbox_x0 * sx}px`,
      top: `${block.bbox_y0 * sy + Math.max(12, (block.bbox_y1 - block.bbox_y0) * sy) + 2}px`,
      width: `${Math.max(24, (block.bbox_x1 - block.bbox_x0) * sx)}px`,
      minHeight: `${Math.max(24, (block.bbox_y1 - block.bbox_y0) * sy * 0.85)}px`,
      fontSize: `${fontPx}px`,
      lineHeight: String(LEVEL_LINE[level]),
      textAlign: centered ? 'center' : 'left',
    }
  }

  const box = packedLayout.value.get(block.id)
  if (!box) return { display: 'none' }
  return {
    left: `${box.left}px`,
    top: `${box.top}px`,
    width: `${box.width}px`,
    height: `${box.height}px`,
    fontSize: `${box.fontPx}px`,
    lineHeight: String(box.lineHeight),
    textAlign: box.centered ? 'center' : 'left',
  }
}

function blockClass(block: BlockItem) {
  const status = block.translation_status
  const hasText = !!block.translation
  const level = textLevel(block)
  const centered =
    props.mode === 'side' && props.side === 'translation'
      ? !!packedLayout.value.get(block.id)?.centered
      : isCenteredBlock(block)
  return {
    embedded: props.mode === 'embedded' && props.side === 'source',
    cover: props.mode === 'side' && props.side === 'translation' && hasText,
    ghost: props.mode === 'side' && props.side === 'translation' && !hasText && status !== 'error',
    highlight: isHighlighted(block.id),
    pending: !hasText && status !== 'error',
    failed: status === 'error',
    'align-center': centered,
    [`level-${level}`]: true,
  }
}

function placeholder(block: BlockItem) {
  if (block.translation) return ''
  if (block.translation_status === 'error') return t('pdfTranslateFailed')
  return '…'
}

function isHighlighted(blockId: string) {
  return props.highlights.some((h) => h.block_id === blockId)
}

function overlayValue(block: BlockItem): string {
  return layoutText(block, block.translation || '')
}

function onBlur(block: BlockItem, e: Event) {
  const el = e.target as HTMLTextAreaElement
  const next = layoutText(block, el.value)
  if (next !== (block.translation || '')) {
    emit('saveTranslation', { blockId: block.id, text: next })
  }
}

watch(
  () =>
    [props.pdfUrl, props.pageIndex, props.scale, props.side, props.forcedWidth, props.forcedHeight] as const,
  () => {
    heightOverrides.value = {}
    void renderPage()
  },
)

watch(
  () => [props.blocks, cssWidth.value, cssHeight.value, props.side, props.mode] as const,
  () => {
    if (fitTimer) clearTimeout(fitTimer)
    fitTimer = setTimeout(() => {
      void fitOverlayHeights().then(() => {
        // Second pass after overrides applied
        requestAnimationFrame(() => void fitOverlayHeights())
      })
    }, 40)
  },
  { deep: true },
)

onMounted(() => {
  void renderPage()
  resizeObserver = new ResizeObserver(() => {
    if (props.forcedWidth) return
    const w = wrapRef.value?.parentElement?.clientWidth || 0
    if (!w || Math.abs(w - lastParentWidth) < 24) return
    if (resizeTimer) clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => void renderPage(), 180)
  })
  if (wrapRef.value?.parentElement) resizeObserver.observe(wrapRef.value.parentElement)
})

onBeforeUnmount(() => {
  if (resizeTimer) clearTimeout(resizeTimer)
  if (fitTimer) clearTimeout(fitTimer)
  resizeObserver?.disconnect()
  renderToken += 1
  if (renderTask) {
    try {
      renderTask.cancel()
    } catch {
      /* ignore */
    }
  }
  safeCleanupDoc(pdfDoc)
  pdfDoc = null
})
</script>

<template>
  <div
    ref="wrapRef"
    class="page-frame"
    :style="{
      width: cssWidth ? cssWidth + 'px' : 'min(720px, 100%)',
      height: cssHeight ? cssHeight + 'px' : 'auto',
    }"
  >
    <div v-if="loading && !cssWidth" class="pdf-status">{{ t('pdfRendering') }}</div>
    <div v-if="renderError" class="pdf-status pdf-status-error">{{ renderError }}</div>
    <canvas ref="canvasRef" />

    <!-- White out English at source bboxes; Chinese is packed on top to close gaps. -->
    <div
      v-if="side === 'translation' && mode === 'side'"
      class="erase-layer"
    >
      <div
        v-for="block in overlayBlocks"
        :key="'erase-' + block.id"
        class="erase-mask"
        :style="eraseStyle(block)"
      />
    </div>

    <div v-if="side === 'translation' || mode === 'embedded'" class="overlay-layer">
      <div
        v-for="block in overlayBlocks"
        :key="block.id"
        class="trans-block"
        :class="blockClass(block)"
        :data-block-id="block.id"
        :style="blockStyle(block)"
        :title="block.text.slice(0, 160)"
        @click="emit('selectBlock', block)"
      >
        <textarea
          :value="overlayValue(block)"
          :placeholder="placeholder(block)"
          @blur="onBlur(block, $event)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-status {
  padding: 1.25rem 1rem;
  color: var(--muted, #6b7685);
  font-size: 0.9rem;
}
.pdf-status-error {
  color: var(--danger, #b42318);
  background: #fdeceb;
}
.page-frame {
  position: relative;
  overflow: visible;
}
.page-frame canvas {
  display: block;
  position: absolute;
  left: 0;
  top: 0;
}
.erase-layer {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 1;
}
.erase-mask {
  position: absolute;
  background: #ffffff;
}
.overlay-layer {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 2;
}
.trans-block {
  position: absolute;
  pointer-events: auto;
  color: #15202b;
  font-family: var(--font-trans), "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif;
  border: none;
  padding: 0;
  box-sizing: border-box;
  overflow: hidden;
  z-index: 2;
}
.trans-block.cover {
  background: #ffffff;
  box-shadow: none;
  border-radius: 0;
  /* No padding — padding + border-box previously ate height and clipped glyphs */
  padding: 0;
}
.trans-block.level-heading {
  font-weight: 650;
  color: #143a56;
  letter-spacing: -0.015em;
  white-space: normal;
}
.trans-block.level-title {
  font-weight: 700;
  color: #0b1520;
  letter-spacing: -0.02em;
  /* Allow wrap — nowrap + tight bbox clipped Chinese titles */
  white-space: normal;
}
.trans-block.align-center,
.trans-block.align-center textarea {
  text-align: center;
}
.trans-block.align-center {
  /* Prefer showing full glyphs over clipping mid-character */
  overflow: visible;
}
.trans-block.level-body {
  font-weight: 400;
  color: #1a2430;
}
.trans-block.level-caption {
  font-weight: 400;
  font-style: italic;
  color: #3d4a59;
}
.trans-block.level-meta {
  font-weight: 400;
  color: #4a5563;
}
.trans-block.ghost {
  background: transparent;
  outline: 1px dashed rgba(26, 77, 110, 0.2);
  outline-offset: -1px;
}
.trans-block.ghost textarea {
  color: transparent;
  caret-color: #1a2b3c;
}
.trans-block.ghost textarea::placeholder {
  color: transparent;
}
.trans-block.embedded {
  background: rgba(255, 252, 245, 0.94);
  border-left: 2px solid var(--accent, #1a4d6e);
  border-radius: 0 4px 4px 0;
  overflow: auto;
  padding: 0.15rem 0.35rem;
}
.trans-block textarea {
  width: 100%;
  height: 100%;
  min-height: 0;
  border: none;
  resize: none;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: inherit;
  font-style: inherit;
  letter-spacing: inherit;
  line-height: inherit;
  padding: 0;
  margin: 0;
  overflow: hidden;
  box-sizing: border-box;
}
.trans-block.level-heading textarea,
.trans-block.level-title textarea {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: clip;
}
.trans-block.embedded textarea {
  overflow: auto;
  min-height: 2rem;
  height: auto;
}
.trans-block textarea:focus {
  outline: 1px solid rgba(26, 77, 110, 0.35);
}
.trans-block.failed {
  outline: 1px solid rgba(180, 35, 24, 0.35);
  outline-offset: -1px;
}
.trans-block.failed textarea::placeholder {
  color: #b42318;
  font-size: 0.85em;
}
.trans-block.highlight {
  outline: 1px solid rgba(26, 77, 110, 0.45);
  outline-offset: 0;
}
</style>
