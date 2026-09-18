/** Re-insert newlines before Demo/Code/Website rows if flattened. */
export function restoreStructuralBreaks(text: string): string {
  return (text || '').replace(
    /(?<!^)\s+(?=(?:Demo|Code|Website|Websites|GitHub|Paper|Project|Homepage|演示|代码|网站|主页|项目)\s*[:：]\s*https?:\/\/)/giu,
    '\n',
  )
}

function isStructuralLine(line: string): boolean {
  const s = (line || '').trim()
  if (!s) return true
  if (
    /^(?:Demo|Code|Website|Websites|GitHub|Paper|Project|Homepage|Source|Dataset|演示|代码|网站|主页|项目|数据|论文)\s*[:：]/iu.test(
      s,
    )
  ) {
    return true
  }
  if (/^https?:\/\/\S+/i.test(s)) return true
  if (/^[\w\u4e00-\u9fff .]{1,24}\s*[:：]\s*\S/u.test(s) && s.length <= 140) {
    if (s.includes('://') || s.includes('@') || s.split(/\s+/).length <= 7) return true
  }
  return false
}

function shouldJoinSoftWrap(prev: string, nxt: string): boolean {
  const p = (prev || '').replace(/\s+$/u, '')
  const n = (nxt || '').replace(/^\s+/u, '')
  if (!p || !n) return false
  if (isStructuralLine(p) || isStructuralLine(n)) return false
  if (/[.!?。！？]$/u.test(p)) return false
  if (p.length <= 28 || n.length <= 28) return true
  if (/^[a-z，、；,;)\]}]/u.test(n)) return true
  if (!/[.!?。！？:：]$/u.test(p) && p.length < 70) return true
  return false
}

/** Join PDF soft wraps; keep real list / link / blank-line breaks. */
export function softUnwrap(text: string): string {
  let raw = (text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  if (!raw.trim()) return ''
  raw = restoreStructuralBreaks(raw)
  raw = raw.replace(/-\n\s*/g, '')

  const parts = raw.split('\n')
  const out: string[] = []
  let buf = (parts[0] || '').replace(/\s+$/u, '')
  for (let i = 1; i < parts.length; i++) {
    const line = parts[i]
    if (shouldJoinSoftWrap(buf, line)) {
      const joiner = buf.endsWith('-') ? '' : ' '
      buf = `${buf.replace(/-$/, '')}${joiner}${line.replace(/^\s+/u, '')}`.replace(/\s+$/u, '')
    } else {
      out.push(buf)
      buf = line.replace(/\s+$/u, '')
    }
  }
  out.push(buf)

  const fixed = out.map((ln) => {
    let s = ln.replace(/[ \t\u00a0]+/g, ' ').trim()
    let prev = ''
    while (prev !== s) {
      prev = s
      s = s.replace(/([\u4e00-\u9fff])\s+([\u4e00-\u9fff])/gu, '$1$2')
    }
    s = s.replace(/([，。；：、！？])\s+/gu, '$1')
    s = s.replace(/\s+([，。；：、！？])/gu, '$1')
    return s
  })
  return fixed.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

/** Strip invented math from translations so PDF equation glyphs stay visible. */
export function sanitizeMathTranslation(source: string, translated: string): string {
  const src = source || ''
  let out = (translated || '').trim()
  if (!out) return out

  const srcHasDollar = src.includes('$')
  const srcHasEq = /[=∫∑∏√≤≥±×÷]|softmax|\\frac|\\sum/i.test(src)
  const srcIsWhereDef = /\bwhere\s+[A-Za-z]|\bin which\s+[A-Za-z]/i.test(src)
  const srcIntroOnly =
    /(denoted as follows|as follows|can be (?:written|expressed|represented)|is given by|given by|defined as)\s*:?\s*$/i.test(
      softUnwrap(src),
    )

  if (!srcHasDollar) {
    out = out.replace(/\$\$[\s\S]*?\$\$/g, '')
    out = out.replace(/\$([^$\n]+)\$/g, '$1')
  }
  out = out.replace(/\\_/g, '_').replace(/\\\{/g, '{').replace(/\\\}/g, '}')

  // Keep full "where Q, K, V are…" translations; only strip glosses after short intros.
  if (!srcHasEq && !srcIsWhereDef) {
    out = out.replace(/((?:如下|为下|表示为|记为|如下所示)[:：])\s*[\s\S]*$/u, '$1')
    const kept: string[] = []
    for (const line of out.split('\n')) {
      const s = line.trim()
      if (!s) {
        if (kept.length) kept.push(line)
        continue
      }
      if (/^\$\$/.test(s) || /^\$[^$]+\$/.test(s) || /^[A-Za-z][A-Za-z0-9_]*\s*=/.test(s)) break
      if (srcIntroOnly && /^(其中|式中|这里|此处).{0,8}[A-Za-z].{0,6}(为|是|表示)/u.test(s)) break
      if (srcIntroOnly && /(其中|式中)\s*[A-Za-z]/u.test(s) && /(为|是|表示)/u.test(s)) break
      kept.push(line)
    }
    out = kept.join('\n').trimEnd()
  }

  return softUnwrap(out.replace(/\n{3,}/g, '\n\n'))
}
