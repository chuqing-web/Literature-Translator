<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { api, type BlockItem } from '../api/client'

const props = defineProps<{
  documentId: string
  blocks: BlockItem[]
  activeBlockId?: string | null
  /** 1-based page number shown in the sheet footer */
  pageNumber?: number
  /** User body base size from settings (px). Scales relative to default 14. */
  baseFontSize?: number
  /** Left PDF canvas CSS size — drives matching scale for fonts & visuals. */
  pageCssSize?: { width: number; height: number } | null
}>()

const emit = defineEmits<{
  selectBlock: [block: BlockItem]
  saveTranslation: [payload: { blockId: string; text: string }]
  focusBlock: [block: BlockItem]
  paneScroll: []
}>()

const rootRef = ref<HTMLElement | null>(null)

type Role = 'title' | 'heading' | 'body' | 'caption' | 'meta' | 'placeholder' | 'page_number'

/** Fallback PDF point sizes when block.font_size is missing. */
const ROLE_PT: Record<Exclude<Role, 'placeholder' | 'page_number'>, number> = {
  title: 16,
  heading: 12,
  body: 10,
  caption: 9,
  meta: 9,
}

function roleOf(block: BlockItem): Role {
  const t = block.block_type
  if (t === 'page_number') return 'page_number'
  if (t === 'placeholder_figure' || t === 'placeholder_table' || t === 'formula_skip') {
    return 'placeholder'
  }
  if (t === 'title' || t === 'heading' || t === 'caption') return t
  if (t === 'meta') return 'meta'
  const text = (block.text || '').replace(/\s+/g, ' ').trim()
  if (/^\d+(\.\d+)*\s+\S/.test(text) && text.length < 90) return 'heading'
  if (block.page_index === 0 && block.block_index === 0 && (block.font_size || 0) >= 14) {
    return 'title'
  }
  if (
    block.page_index === 0 &&
    block.block_index > 0 &&
    block.block_index <= 5 &&
    text.length < 500 &&
    (block.bbox_y1 - block.bbox_y0) < 55
  ) {
    return 'meta'
  }
  return 'body'
}

function pageDims(block: BlockItem): { pageW: number; pageH: number } {
  return {
    pageW: block.page_width || 612,
    pageH: block.page_height || 792,
  }
}

/** PDF-pt → CSS-px using the left canvas display size. */
function scales(block: BlockItem): { sx: number; sy: number } {
  const { pageW, pageH } = pageDims(block)
  const cssW = props.pageCssSize?.width || 0
  const cssH = props.pageCssSize?.height || 0
  // Before left page paints, approximate letter @ ~720 CSS px wide
  const sx = cssW > 0 ? cssW / pageW : 720 / pageW
  const sy = cssH > 0 ? cssH / pageH : sx
  return { sx, sy }
}

/** Settings default 14 → 1.0; user can still bump/shrink proportionally. */
function userFontScale(): number {
  const base = props.baseFontSize || 14
  return Math.min(1.35, Math.max(0.85, base / 14))
}

/** Match left PDF glyph size (pt × display scale), then apply user preference. */
function fontPxFor(block: BlockItem): number {
  const role = roleOf(block)
  const { sy } = scales(block)
  const src = block.font_size || 0
  let pt = src
  if (pt <= 0) {
    if (role === 'placeholder' || role === 'page_number') pt = ROLE_PT.body
    else pt = ROLE_PT[role]
  }
  const px = pt * sy * userFontScale()
  return Math.round(Math.min(28, Math.max(9, px)) * 10) / 10
}

function gapBeforePx(block: BlockItem, prev: BlockItem | null): number {
  if (!prev) return 8
  const { sy } = scales(block)
  const gapPt = block.bbox_y0 - prev.bbox_y1
  if (gapPt <= 0) return 4
  // Preserve PDF vertical rhythm; clamp extremes so flow stays readable
  const px = gapPt * sy
  if (gapPt > 48) return Math.min(56, Math.max(28, px * 0.85))
  if (gapPt > 22) return Math.min(36, Math.max(16, px * 0.9))
  if (gapPt > 10) return Math.min(22, Math.max(10, px))
  return Math.min(14, Math.max(4, px))
}

/** Exact on-canvas box for figures / tables / formulas.
 *  Matches preview.png clip (bbox ±2pt pad) so the PNG fills 1:1. */
function visualBox(block: BlockItem): { width: number; height: number; left: number } {
  const { sx, sy } = scales(block)
  const { pageW, pageH } = pageDims(block)
  const pad = 2
  const x0 = Math.max(0, block.bbox_x0 - pad)
  const y0 = Math.max(0, block.bbox_y0 - pad)
  const x1 = Math.min(pageW, block.bbox_x1 + pad)
  const y1 = Math.min(pageH, block.bbox_y1 + pad)
  return {
    width: Math.round(Math.max(20, (x1 - x0) * sx)),
    height: Math.round(Math.max(16, (y1 - y0) * sy)),
    left: Math.round(x0 * sx),
  }
}

/** Text column geometry matching source bbox on the left canvas. */
function textBox(block: BlockItem): { width: number; left: number } {
  const { sx } = scales(block)
  const { pageW } = pageDims(block)
  const cssW = props.pageCssSize?.width || pageW * sx
  const left = Math.max(0, block.bbox_x0 * sx)
  const rawW = (block.bbox_x1 - block.bbox_x0) * sx
  // Keep readable min width; don't spill past page edge
  const width = Math.max(48, Math.min(rawW, cssW - left))
  return {
    width: Math.round(width),
    left: Math.round(left),
  }
}

function previewUrl(block: BlockItem): string {
  return api.blockPreviewUrl(props.documentId, block.id, 2.5)
}

const sheetStyle = computed(() => {
  const w = props.pageCssSize?.width
  const h = props.pageCssSize?.height
  return {
    width: w ? `${w}px` : 'min(42rem, 100%)',
    minHeight: h ? `${h}px` : 'min(90vh, 1100px)',
  }
})

const flowItems = computed(() => {
  const list = [...props.blocks]
    .filter((b) => b.block_type !== 'page_number')
    .sort((a, b) => a.block_index - b.block_index)
  return list.map((block, i) => {
    const prev = i > 0 ? list[i - 1] : null
    const role = roleOf(block)
    const visual =
      role === 'placeholder' &&
      (block.block_type === 'placeholder_figure' ||
        block.block_type === 'placeholder_table' ||
        block.block_type === 'formula_skip')
    const vBox = visual ? visualBox(block) : null
    const tBox = !visual ? textBox(block) : null
    return {
      block,
      role,
      fontPx: fontPxFor(block),
      marginTop: gapBeforePx(block, prev),
      isPlaceholder: role === 'placeholder',
      showImage: visual,
      visualBox: vBox,
      textBox: tBox,
    }
  })
})

const pageNumFromBlocks = computed(() => {
  const nums = props.blocks
    .filter((b) => b.block_type === 'page_number' && /^\d+$/.test((b.text || '').trim()))
    .sort((a, b) => b.bbox_y0 - a.bbox_y0)
  if (nums[0]?.text) return nums[0].text.trim()
  if (props.pageNumber && props.pageNumber > 0) return String(props.pageNumber)
  const first = props.blocks[0]
  return first ? String(first.page_index + 1) : null
})

function onBlur(block: BlockItem, e: Event) {
  const el = e.target as HTMLTextAreaElement
  if (el.value !== (block.translation || '')) {
    emit('saveTranslation', { blockId: block.id, text: el.value })
  }
}

function onSelect(block: BlockItem) {
  emit('selectBlock', block)
  emit('focusBlock', block)
}

function scrollToBlockId(blockId: string) {
  const el = rootRef.value?.querySelector(`[data-block-id="${blockId}"]`) as HTMLElement | null
  if (!el || !rootRef.value) return
  const parent = rootRef.value
  const top = el.offsetTop - 24
  parent.scrollTo({ top: Math.max(0, top), behavior: 'auto' })
}

function blockIdNearScroll(): string | null {
  const parent = rootRef.value
  if (!parent) return null
  const target = parent.scrollTop + 40
  let best: { id: string; dist: number } | null = null
  for (const node of parent.querySelectorAll<HTMLElement>('[data-block-id]')) {
    const dist = Math.abs(node.offsetTop - target)
    if (!best || dist < best.dist) best = { id: node.dataset.blockId || '', dist }
  }
  return best?.id || null
}

watch(
  () => props.blocks,
  async () => {
    await nextTick()
    rootRef.value?.querySelectorAll('textarea').forEach((node) => {
      const el = node as HTMLTextAreaElement
      el.style.height = 'auto'
      el.style.height = `${el.scrollHeight}px`
    })
  },
  { deep: true },
)

watch(
  () => [props.activeBlockId, props.pageCssSize?.width, props.pageCssSize?.height] as const,
  async ([id]) => {
    await nextTick()
    rootRef.value?.querySelectorAll('textarea').forEach((node) => {
      const el = node as HTMLTextAreaElement
      el.style.height = 'auto'
      el.style.height = `${el.scrollHeight}px`
    })
    if (id) scrollToBlockId(id)
  },
)

defineExpose({ scrollToBlockId, blockIdNearScroll, rootRef })
</script>

<template>
  <div ref="rootRef" class="trans-pane" @scroll="emit('paneScroll')">
    <div class="trans-sheet" :style="sheetStyle">
      <article
        v-for="item in flowItems"
        :key="item.block.id"
        class="trans-item"
        :class="[
          `role-${item.role}`,
          {
            active: activeBlockId === item.block.id,
            pending: !item.isPlaceholder && !item.block.translation,
            failed: item.block.translation_status === 'error',
          },
        ]"
        :data-block-id="item.block.id"
        :style="{
          marginTop: item.marginTop + 'px',
          fontSize: item.fontPx + 'px',
          marginLeft: (item.visualBox?.left ?? item.textBox?.left ?? 0) + 'px',
          width: item.visualBox
            ? item.visualBox.width + 'px'
            : item.textBox
              ? item.textBox.width + 'px'
              : '100%',
        }"
        @click="onSelect(item.block)"
      >
        <div
          v-if="item.isPlaceholder"
          class="placeholder"
          :class="{ 'has-image': item.showImage }"
          :style="
            item.visualBox
              ? {
                  width: item.visualBox.width + 'px',
                  height: item.visualBox.height + 'px',
                }
              : undefined
          "
        >
          <img
            v-if="item.showImage"
            class="placeholder-img"
            :src="previewUrl(item.block)"
            :alt="
              item.block.block_type === 'placeholder_table'
                ? '表格原图'
                : item.block.block_type === 'formula_skip'
                  ? '公式原图'
                  : '图示原图'
            "
            loading="lazy"
            @error="($event.target as HTMLImageElement).style.display = 'none'"
          />
          <span v-else-if="item.block.block_type === 'placeholder_figure'">图示（保留原位，不翻译）</span>
          <span v-else-if="item.block.block_type === 'placeholder_table'">表格（保留原位，不翻译）</span>
          <span v-else>公式 / 非文本（跳过）</span>
        </div>
        <textarea
          v-else
          :value="item.block.translation || ''"
          :placeholder="
            item.block.translation_status === 'error'
              ? '翻译失败'
              : item.block.translation
                ? ''
                : '…'
          "
          rows="1"
          @input="(e) => {
            const el = e.target as HTMLTextAreaElement
            el.style.height = 'auto'
            el.style.height = el.scrollHeight + 'px'
          }"
          @focus="onSelect(item.block)"
          @blur="onBlur(item.block, $event)"
        />
      </article>
      <p v-if="!flowItems.length" class="empty">本页无可译文本块</p>
      <footer v-if="pageNumFromBlocks" class="page-num" aria-label="页码">{{ pageNumFromBlocks }}</footer>
    </div>
  </div>
</template>

<style scoped>
.trans-pane {
  height: 100%;
  overflow: auto;
  /* Match .pages.side > div padding; sheet width already equals left canvas */
  padding: 0 0 2rem;
  background:
    linear-gradient(180deg, #e8edf3 0%, #eef2f6 100%);
}
.trans-sheet {
  margin: 0 auto;
  max-width: 100%;
  background: #fff;
  border-radius: 2px;
  box-shadow:
    0 0 0 1px rgba(18, 22, 28, 0.06),
    0 18px 40px rgba(18, 22, 28, 0.1);
  /* No horizontal padding — block bboxes already include PDF page margins */
  padding: 0 0 2rem;
  position: relative;
  box-sizing: border-box;
}
.trans-item {
  position: relative;
  color: #15202b;
  font-family: var(--font-trans), "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
  line-height: var(--trans-leading, 1.55);
  box-sizing: border-box;
  max-width: 100%;
}
.trans-item textarea {
  display: block;
  width: 100%;
  border: none;
  resize: none;
  background: transparent;
  color: inherit;
  font: inherit;
  line-height: inherit;
  padding: 0.1rem 0;
  margin: 0;
  overflow: hidden;
  min-height: 1.4em;
  box-sizing: border-box;
}
.trans-item textarea:focus {
  outline: 1px solid rgba(26, 77, 110, 0.3);
  background: rgba(244, 249, 252, 0.65);
}
.trans-item.role-title {
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #0b1520;
  line-height: 1.3;
}
.trans-item.role-heading {
  font-weight: 650;
  color: #143a56;
  border-left: 3px solid var(--accent, #1a4d6e);
  padding-left: 0.45rem;
  line-height: 1.35;
  box-sizing: border-box;
}
.trans-item.role-caption {
  font-style: italic;
  color: #3d4a59;
}
.trans-item.role-meta {
  color: #4a5563;
}
.trans-item.role-body {
  color: #1a2430;
}
.trans-item.active {
  background: rgba(228, 238, 245, 0.55);
  border-radius: 4px;
}
.trans-item.pending textarea::placeholder {
  color: #9aa5b3;
}
.trans-item.failed textarea::placeholder {
  color: #b42318;
}
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #b8c3d1;
  border-radius: 2px;
  background:
    repeating-linear-gradient(
      -45deg,
      #f7f9fc,
      #f7f9fc 8px,
      #eef2f6 8px,
      #eef2f6 16px
    );
  color: #6b7685;
  font-size: 0.82rem;
  font-style: normal;
  font-family: var(--font-ui, system-ui, sans-serif);
  letter-spacing: 0.02em;
  overflow: hidden;
  box-sizing: border-box;
}
.placeholder.has-image {
  border: none;
  background: transparent;
  padding: 0;
  border-radius: 0;
}
.placeholder-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center top;
  background: #fff;
}
.empty {
  color: #6b7685;
  text-align: center;
  padding: 3rem 1rem;
}
.page-num {
  margin-top: 2rem;
  padding: 0.85rem 0 0.25rem;
  border-top: 1px solid rgba(18, 22, 28, 0.08);
  text-align: center;
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: 0.95rem;
  color: #4a5563;
  letter-spacing: 0.04em;
  user-select: none;
}
</style>
