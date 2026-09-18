<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as pdfjs from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import type { BlockItem, HighlightItem } from '../api/client'
import { t } from '../i18n'
import { sanitizeMathTranslation, softUnwrap } from '../utils/mathText'

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker

const props = defineProps<{
  pdfUrl: string
  pageIndex: number
  scale?: number
  forcedWidth?: number
  forcedHeight?: number
  blocks: BlockItem[]
  highlights: HighlightItem[]
  /** Current selection — outlined on both panes in side mode. */
  selectedBlockId?: string | null
  mode: 'embedded' | 'side'
  side: 'source' | 'translation'
}>()

/** Side-by-side source pane: transparent hit targets over PDF bboxes (no translation UI). */
const isSourceHit = computed(
  () => props.mode === 'side' && props.side === 'source',
)

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
  title: 16.5,
  heading: 13,
  body: 11,
  caption: 10,
  meta: 10,
}

/** Translation overlays sit 0.5px under the matched PDF size. */
const TRANS_FONT_DELTA = -0.5

const LEVEL_LINE: Record<TextLevel, number> = {
  title: 1.2,
  heading: 1.2,
  body: 1.28,
  caption: 1.25,
  meta: 1.1,
}

type PackedBox = {
  left: number
  top: number
  width: number
  height: number
  /** Hard ceiling for fitOverlayHeights — never grow past reserved PDF bands. */
  capHeight: number
  eraseLeft: number
  eraseTop: number
  eraseWidth: number
  eraseHeight: number
  level: TextLevel
  fontPx: number
  lineHeight: number
  centered: boolean
}

/** Actual textarea scrollHeight overrides (px) after paint — fixes canvas under-measure. */
const heightOverrides = ref<Record<string, number>>({})
let fitTimer: ReturnType<typeof setTimeout> | null = null

/**
 * True when the PDF bbox is horizontally centered on the page.
 * Single-column body also has equal L/R margins — that is NOT decorative centering;
 * use wantsCenterAlign() so only title/meta/caption lines actually center.
 */
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

/** Center-align only decorative lines (title / heading / authors / captions), never body. */
function wantsCenterAlign(block: BlockItem, level: TextLevel = textLevel(block)): boolean {
  if (level === 'body') return false
  return isCenteredBlock(block)
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

/** Author name lists stay as PDF glyphs on the translation pane — never re-laid. */
function isAuthorNameBlock(block: BlockItem): boolean {
  if (looksLikeAuthorLine(block.text)) return true
  // First-page meta lines that are clearly person lists
  if (block.block_type === 'meta' && looksLikeAuthorLine(block.text)) return true
  return false
}

/** Blocks that can be selected / hit-tested (includes authors). */
function isSelectableBlock(block: BlockItem): boolean {
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

/** Translation covers — authors are excluded so the PDF names show unchanged. */
function isOverlayBlock(block: BlockItem): boolean {
  if (!isSelectableBlock(block)) return false
  if (isAuthorNameBlock(block)) return false
  return true
}

const overlayBlocks = computed(() => props.blocks.filter(isOverlayBlock))
/** Source-pane hit targets include author lines for selection / notes. */
const hitBlocks = computed(() => props.blocks.filter(isSelectableBlock))

/**
 * Hard ceilings in CSS px — overlays must not paint into these bands.
 * Includes figures/tables, formula_skip glyphs, and every block top (so
 * interstitial PDF equations between text blocks stay uncovered).
 */
const guardTopsCss = computed(() => {
  if (!cssWidth.value || !cssHeight.value || !props.blocks.length) return [] as {
    y: number
    x0: number
    x1: number
    reserved: boolean
  }[]
  const pageH = props.blocks[0]?.page_height || 0
  if (!pageH) return []
  const sy = cssHeight.value / pageH
  return props.blocks
    .filter((b) => {
      const h = b.bbox_y1 - b.bbox_y0
      const w = b.bbox_x1 - b.bbox_x0
      return w >= 8 && h >= 4
    })
    .map((b) => ({
      y: b.bbox_y0 * sy,
      x0: b.bbox_x0,
      x1: b.bbox_x1,
      reserved:
        b.block_type === 'formula_skip' ||
        b.block_type === 'placeholder_figure' ||
        b.block_type === 'placeholder_table' ||
        b.block_type === 'skip' ||
        looksLikeAuthorLine(b.text),
    }))
    .sort((a, b) => a.y - b.y)
})

function looksLikeAuthorLine(text: string): boolean {
  const compact = (text || '').replace(/\s+/g, ' ').trim()
  if (!compact || compact.length > 420) return false
  const lower = compact.toLowerCase()
  if (
    lower.includes('university') ||
    lower.includes('institute') ||
    lower.includes('department') ||
    lower.includes('http') ||
    lower.includes('@')
  ) {
    return false
  }
  if (!compact.includes(',') && !/\band\b/i.test(compact)) return false
  const cleaned = compact.replace(/[∗*†‡§¶\d]+/g, '')
  const parts = cleaned
    .split(/,|\band\b/i)
    .map((p) => p.trim())
    .filter(Boolean)
  if (parts.length < 2) return false
  let nameish = 0
  for (const part of parts) {
    const words = part.split(/\s+/).filter(Boolean)
    if (!words.length || words.length > 5) continue
    if (words.every((w) => /^[A-ZÀ-ÖØ-Þ]/.test(w) || /^(and|of|the)$/i.test(w))) nameish += 1
  }
  return nameish >= Math.max(2, Math.floor(parts.length * 0.65))
}

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
function measureContentHeight(
  text: string,
  boxW: number,
  fontPx: number,
  lineHeight: number,
  fontWeight: number = 400,
): number {
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
    `font:${fontWeight} ${fontPx}px "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif`,
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
      ctx.font = `${fontWeight} ${fontPx}px "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif`
      canvasLines = wrapLines(ctx, raw, Math.max(12, boxW - 4))
    }
  } catch {
    /* ignore */
  }
  const fromCanvas = Math.ceil(canvasLines * oneLine)
  // Small tail only — large slack per block stacked into page-sized gaps.
  return Math.max(h, fromCanvas, oneLine) + Math.ceil(fontPx * 0.18) + 2
}

/**
 * Headings/titles must stay one visual line. Soft PDF wraps are joined via
 * softUnwrap; real list / link breaks are preserved.
 */
function layoutText(block: BlockItem, raw: string): string {
  let t = softUnwrap(raw || '')
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
 * Snap height to whole line boxes so overflow:hidden never slices mid-glyph.
 * Does not change font size — callers must keep translations short instead.
 */
function snapHeightToLines(
  avail: number,
  fontPx: number,
  lineHeight: number,
  preferMinLines = 1,
): number {
  const unit = Math.max(1, fontPx * lineHeight)
  const descPad = Math.ceil(fontPx * 0.22)
  const maxLines = Math.max(preferMinLines, Math.floor((avail + 0.01) / unit))
  if (maxLines <= 0) return Math.max(10, avail)
  const snapped = maxLines * unit + descPad
  return Math.min(avail, Math.max(unit * preferMinLines, snapped))
}

/**
 * Pack translation boxes: hide English with full-bbox erase masks, place Chinese
 * at measured content height (whole-line snap — never mid-glyph). Packing is
 * per-column; font size is never reduced — keep translations concise instead.
 */
const packedLayout = computed(() => {
  const map = new Map<string, PackedBox>()
  // Source hit layer uses PDF bboxes — skip translation packing.
  if (isSourceHit.value) return map
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

  function columnOfBox(x0: number, x1: number): 'full' | 'left' | 'right' {
    const cx = (x0 + x1) / 2
    const w = x1 - x0
    if (w >= pageW * 0.55) return 'full'
    return cx < midX ? 'left' : 'right'
  }

  /** Next PDF band below this block in the same column (formula / next paragraph). */
  function nextGuard(
    srcTop: number,
    col: 'full' | 'left' | 'right',
  ): { y: number; reserved: boolean } | null {
    for (const g of guardTopsCss.value) {
      if (g.y <= srcTop + 2) continue
      const gCol = columnOfBox(g.x0, g.x1)
      if (col === 'full' || gCol === 'full' || gCol === col) {
        return { y: g.y, reserved: g.reserved }
      }
    }
    return null
  }

  for (const block of sorted) {
    const level = textLevel(block)
    const centered = wantsCenterAlign(block, level)
    const srcPt = block.font_size || 0
    const basePx =
      srcPt > 0 ? Math.min(22, Math.max(9, srcPt * sy)) : LEVEL_SIZE[level]
    const fontPx = Math.round(Math.max(8.5, basePx + TRANS_FONT_DELTA) * 10) / 10
    const lineHeight = LEVEL_LINE[level]
    let left = block.bbox_x0 * sx - pad
    let width = Math.max(24, (block.bbox_x1 - block.bbox_x0) * sx + pad * 2)
    const eraseLeft = left
    const eraseWidth = width

    const rawTrans = looksLikeAuthorLine(block.text)
      ? block.text
      : sanitizeMathTranslation(block.text, block.translation || '')
    const text = layoutText(block, rawTrans)
    const fallback = layoutText(block, block.text || '…')
    const display = text || fallback

    if (centered && (level === 'title' || level === 'heading')) {
      // Titles only: a tight English bbox clips wrapped Chinese — widen, never shrink font.
      const margin = Math.max(14, cssWidth.value * 0.035)
      const maxW = Math.max(48, cssWidth.value - margin * 2)
      const natural = measureTextWidthPx(display, fontPx) + 16
      width = Math.min(maxW, Math.max(width, Math.min(natural, cssWidth.value * 0.94)))
      left = (cssWidth.value - width) / 2
    } else if (level === 'heading' || level === 'title') {
      // Prefer one visual line: give headings extra horizontal room.
      const natural = measureTextWidthPx(display, fontPx) + 14
      width = Math.max(
        width,
        Math.min(cssWidth.value * 0.62, Math.max(fontPx * 14, natural)),
      )
    }

    const measureW = width
    const srcTop = block.bbox_y0 * sy - pad
    const srcHeight = Math.max(12, (block.bbox_y1 - block.bbox_y0) * sy + pad * 2)
    const srcBottom = srcTop + srcHeight
    const col = columnOf(block)

    const weight = level === 'title' ? 700 : level === 'heading' ? 650 : 400
    const measured = measureContentHeight(display, measureW, fontPx, lineHeight, weight)
    // Only short title/heading lines need glyph slack — never inflate author/body.
    const oneLineNeed = Math.ceil(fontPx * lineHeight + fontPx * 0.28)
    const hardLines = Math.max(1, display.split(/\n/).filter((ln) => ln.trim().length > 0).length)
    const hardLineH = Math.ceil(hardLines * fontPx * lineHeight + fontPx * 0.35)
    const shortTitle =
      (level === 'title' || level === 'heading') && measured <= fontPx * lineHeight * 1.35
    let contentH = Math.max(measured, overrides[block.id] || 0, hardLineH)
    if (shortTitle) contentH = Math.max(contentH, oneLineNeed)
    // Author / meta: PDF bboxes hug the baseline and clip CSS ascenders.
    // Keep one full glyph line (no font shrink); do not grow into a paragraph.
    const isAuthor = looksLikeAuthorLine(block.text)
    if (isAuthor) {
      const glyphH = Math.ceil(fontPx * 1.72)
      contentH = glyphH
      const natural = measureTextWidthPx(display, fontPx) + 10
      const maxW = Math.max(width, cssWidth.value - Math.max(0, left) - 6)
      if (natural > width) width = Math.min(maxW, natural)
    }
    // Titles/headings: never request more than ~2 lines — length budget is the lever.
    if (level === 'title' || level === 'heading') {
      contentH = Math.min(contentH, Math.ceil(fontPx * lineHeight * 2 + fontPx * 0.35))
    }

    // Side columns stay independent. A full-width line clears both columns.
    const floor =
      col === 'full'
        ? Math.max(cols.full.prevBottom, cols.left.prevBottom, cols.right.prevBottom)
        : Math.max(cols[col].prevBottom, cols.full.prevBottom)

    let top = srcTop
    if (floor > 1 && floor + 3 > srcTop) {
      top = floor + 3
    }

    // Never paint into the next PDF band (figures, formulas, next paragraph).
    // Large gaps between source bboxes usually hold equation glyphs with no
    // block id — reserve that strip instead of letting Chinese grow into it.
    const guard = nextGuard(srcTop, col)
    let cap = Number.POSITIVE_INFINITY
    if (guard != null) {
      const gapBelow = guard.y - srcBottom
      // Structural multi-line blocks (Demo/Code/Website) already own their PDF
      // seat — do not treat the following section gap as a formula clamp that
      // would shrink the cover below the source bbox.
      const ownSeat = hardLines >= 2 || gapBelow <= Math.max(14, fontPx * 1.15)
      const formulaGap = guard.reserved || (!ownSeat && gapBelow > Math.max(14, fontPx * 1.15))
      const limit = formulaGap ? srcBottom + 3 : guard.y - 6
      cap = Math.max(10, limit - top)
      if (top >= limit) {
        top = Math.max(srcTop, limit - Math.max(srcHeight, Math.min(contentH, limit - srcTop)))
        cap = Math.max(10, limit - top)
      }
      // Prefer the source seat when a formula gap must stay clear.
      if (formulaGap) {
        top = srcTop
        cap = Math.max(10, limit - srcTop)
      } else if (srcBottom <= limit && top + contentH > limit) {
        top = srcTop
        cap = Math.max(10, limit - srcTop)
      }
    }

    // Fit content into cap without shrinking font: whole-line snap only.
    let boxH = Math.min(contentH, cap)
    if (level === 'title' || level === 'heading') {
      // One full line with descenders whenever the seat allows.
      boxH = Math.max(boxH, Math.min(oneLineNeed, cap))
      boxH = snapHeightToLines(boxH, fontPx, lineHeight, 1)
      boxH = Math.min(boxH, cap)
    } else if (Number.isFinite(cap) && contentH > cap + 0.5) {
      boxH = snapHeightToLines(cap, fontPx, lineHeight, Math.min(hardLines, 8))
    } else {
      // Small descender pad so the last line is not sliced.
      boxH = Math.min(cap, Math.max(boxH, Math.min(contentH + Math.ceil(fontPx * 0.18), cap)))
    }

    // Side-by-side: cover must be at least as tall as the PDF seat so the
    // selection outline matches the source pane (Demo/Code/Website, etc.).
    if (props.mode === 'side' && props.side === 'translation' && !isAuthor) {
      const seat = Math.min(srcHeight, Number.isFinite(cap) ? cap : srcHeight)
      boxH = Math.max(boxH, seat)
      // Prefer sitting on the source seat when we only grew to match it.
      if (boxH <= srcHeight + 1) top = srcTop
    }

    // Author names: lift the box so ascenders sit inside it. A tight PDF bbox
    // plus overflow:hidden otherwise shows only the lower half of each letter.
    if (isAuthor) {
      const glyphH = Math.ceil(fontPx * 1.72)
      const lift = Math.ceil(fontPx * 0.34)
      top = Math.max(0, srcTop - lift)
      boxH = glyphH
      if (guard != null && !guard.reserved) {
        const limit = guard.y - 1
        if (top + boxH > limit) {
          top = Math.max(0, limit - boxH)
        }
        if (top + boxH > limit) {
          boxH = Math.max(Math.ceil(fontPx * 1.4), limit - top)
        }
      }
    }

    map.set(block.id, {
      left,
      top,
      width,
      height: boxH,
      capHeight: Number.isFinite(cap) ? Math.max(cap, boxH) : boxH + 2000,
      // White-out the English glyphs at the source seat — not the shifted
      // Chinese box (a recentered title must still erase the original band).
      eraseLeft,
      eraseTop: srcTop,
      eraseWidth,
      eraseHeight: Math.max(srcHeight, boxH - Math.max(0, srcTop - top)),
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

/** Grow boxes to real textarea scroll size, then packing recomputes via overrides.
 * Never shrink fonts; never grow past capHeight (formula/figure guards).
 */
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
    const packed = packedLayout.value.get(id)
    const cap = packed?.capHeight ?? Number.POSITIVE_INFINITY
    const prev = ta.style.height
    ta.style.height = '0px'
    const fontPx = parseFloat(getComputedStyle(ta).fontSize) || 12
    // Small descender slack only — large padding used to push covers into formulas.
    const needRaw = Math.ceil(ta.scrollHeight) + Math.ceil(fontPx * 0.22)
    ta.style.height = prev
    const needH = Math.min(needRaw, cap)
    const cur = packed?.height || 0
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
    left: `${box.eraseLeft}px`,
    top: `${box.eraseTop}px`,
    width: `${box.eraseWidth}px`,
    height: `${box.eraseHeight}px`,
  }
}

function blockStyle(block: BlockItem) {
  if (!cssWidth.value || !cssHeight.value || !block.page_width || !block.page_height) {
    return { display: 'none' }
  }

  // Side source: selection must enclose full glyphs, not the tight PDF bbox
  // (title lines often have bbox height == font size, which slices descenders).
  if (isSourceHit.value) {
    const sx = cssWidth.value / block.page_width
    const sy = cssHeight.value / block.page_height
    const fontPx = Math.max(11, (block.font_size || 12) * sy)
    const rawTop = block.bbox_y0 * sy
    const rawH = Math.max(12, (block.bbox_y1 - block.bbox_y0) * sy)
    const padTop = Math.ceil(fontPx * 0.12)
    const padBot = Math.ceil(fontPx * 0.55)
    return {
      left: `${block.bbox_x0 * sx}px`,
      top: `${rawTop - padTop}px`,
      width: `${Math.max(24, (block.bbox_x1 - block.bbox_x0) * sx)}px`,
      height: `${Math.max(rawH + padTop + padBot, fontPx * 1.7)}px`,
    }
  }

  if (props.mode === 'embedded' && props.side === 'source') {
    const sx = cssWidth.value / block.page_width
    const sy = cssHeight.value / block.page_height
    const level = textLevel(block)
    const fontPx = LEVEL_SIZE[level]
    const centered = wantsCenterAlign(block, level)
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
      : wantsCenterAlign(block, level)
  return {
    embedded: props.mode === 'embedded' && props.side === 'source',
    'source-hit': isSourceHit.value,
    cover: props.mode === 'side' && props.side === 'translation' && hasText,
    ghost: props.mode === 'side' && props.side === 'translation' && !hasText && status !== 'error',
    highlight: isHighlighted(block.id),
    selected: props.selectedBlockId === block.id,
    pending: !isSourceHit.value && !hasText && status !== 'error',
    failed: !isSourceHit.value && status === 'error',
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
  // Author lines stay in Latin spelling even if an older bad translation exists.
  if (looksLikeAuthorLine(block.text)) return layoutText(block, block.text)
  const cleaned = sanitizeMathTranslation(block.text, block.translation || '')
  return layoutText(block, cleaned)
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

    <div
      v-if="side === 'translation' || mode === 'embedded' || isSourceHit"
      class="overlay-layer"
      :class="{ 'hit-layer': isSourceHit }"
    >
      <div
        v-for="block in isSourceHit ? hitBlocks : overlayBlocks"
        :key="block.id"
        class="trans-block"
        :class="blockClass(block)"
        :data-block-id="block.id"
        :style="blockStyle(block)"
        :title="block.text.slice(0, 160)"
        @click="emit('selectBlock', block)"
      >
        <textarea
          v-if="!isSourceHit"
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
  /* Opaque so PDF underlay never bleeds through selection / packing gaps */
  background: #ffffff;
  box-shadow: none;
  border-radius: 0;
  padding: 0;
  overflow: hidden;
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
  white-space: normal;
}
.trans-block.align-center,
.trans-block.align-center textarea {
  text-align: center;
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
.trans-block.level-meta textarea {
  line-height: 1.2;
  padding-top: 0.08em;
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
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  vertical-align: top;
}
.trans-block.level-heading textarea,
.trans-block.level-title textarea {
  white-space: pre-wrap;
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
  outline: none;
}
.trans-block.selected {
  outline: 2px solid rgba(26, 77, 110, 0.85);
  outline-offset: 0;
  z-index: 5;
}
.trans-block.cover.selected {
  /* Solid tint — no see-through to English PDF / neighboring lines */
  background: #dceaf4;
}
.trans-block.ghost.selected,
.trans-block.embedded.selected {
  background: rgba(66, 133, 180, 0.14);
}
.overlay-layer.hit-layer {
  pointer-events: none;
}
.trans-block.source-hit {
  pointer-events: auto;
  background: transparent;
  cursor: pointer;
  overflow: visible;
}
.trans-block.source-hit:hover:not(.selected) {
  outline: 1px dashed rgba(26, 77, 110, 0.35);
  outline-offset: 0;
  background: rgba(66, 133, 180, 0.06);
}
.trans-block.source-hit.selected {
  background: rgba(66, 133, 180, 0.22);
}
.trans-block.cover:hover:not(.selected),
.trans-block.ghost:hover:not(.selected),
.trans-block.embedded:hover:not(.selected) {
  outline: 1px dashed rgba(26, 77, 110, 0.28);
  outline-offset: 0;
}
</style>
