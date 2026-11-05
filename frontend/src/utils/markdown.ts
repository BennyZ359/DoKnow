/**
 * Minimal, dependency-free Markdown renderer for lesson bodies.
 * Lesson content is LLM-generated markdown (§ 课程生成), rendered read-only —
 * we escape all raw HTML first, then apply a safe subset of formatting:
 * headings, paragraphs, lists, fenced code, blockquotes, tables, inline styles.
 */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Inline styles: code spans, bold, italic, links. Input is already escaped. */
function inline(s: string): string {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
}

function renderTable(lines: string[]): string {
  // lines: header | separator | rows, cells split on unescaped '|'
  const cells = (row: string) =>
    row
      .replace(/^\||\|$/g, '')
      .split('|')
      .map((c) => c.trim())
  const [header, , ...rows] = lines
  const head = cells(header)
    .map((c) => `<th>${inline(c)}</th>`)
    .join('')
  const body = rows
    .map((r) => `<tr>${cells(r).map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`)
    .join('')
  return `<div class="md-table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`
}

export function renderMarkdown(src: string | null | undefined): string {
  if (!src) return ''
  const lines = escapeHtml(src).split('\n')
  const out: string[] = []
  let i = 0

  const flushParagraph = (buf: string[]) => {
    if (buf.length) out.push(`<p>${inline(buf.join(' '))}</p>`)
  }

  while (i < lines.length) {
    const line = lines[i]

    if (!line.trim()) {
      i++
      continue
    }

    // fenced code block
    if (line.trim().startsWith('```')) {
      const lang = line.trim().slice(3).trim()
      const buf: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) buf.push(lines[i++])
      i++ // closing fence
      out.push(
        `<pre class="md-code${lang ? ` lang-${lang}` : ''}"><code>${buf.join('\n')}</code></pre>`,
      )
      continue
    }

    // heading
    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`)
      i++
      continue
    }

    // horizontal rule
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      out.push('<hr />')
      i++
      continue
    }

    // blockquote
    if (line.trim().startsWith('&gt;')) {
      const buf: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('&gt;')) {
        buf.push(lines[i].trim().replace(/^&gt;\s?/, ''))
        i++
      }
      out.push(`<blockquote>${inline(buf.join(' '))}</blockquote>`)
      continue
    }

    // table (a line with '|' followed by a |---| separator)
    if (line.includes('|') && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1] ?? '')) {
      const buf: string[] = []
      while (i < lines.length && lines[i].includes('|')) buf.push(lines[i++])
      out.push(renderTable(buf))
      continue
    }

    // unordered list
    if (/^\s*[-*+]\s+/.test(line)) {
      const buf: string[] = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*[-*+]\s+/, ''))
        i++
      }
      out.push(`<ul>${buf.map((x) => `<li>${inline(x)}</li>`).join('')}</ul>`)
      continue
    }

    // ordered list
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const buf: string[] = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*\d+[.)]\s+/, ''))
        i++
      }
      out.push(`<ol>${buf.map((x) => `<li>${inline(x)}</li>`).join('')}</ol>`)
      continue
    }

    // paragraph: accumulate until blank line or a block-level opener
    const buf: string[] = [line]
    i++
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,6})\s|```|&gt;|\s*[-*+]\s|\s*\d+[.)]\s/.test(lines[i]) &&
      !(lines[i].includes('|') && /^\s*\|?[\s:|-]+\|/.test(lines[i + 1] ?? ''))
    ) {
      buf.push(lines[i++])
    }
    flushParagraph(buf)
  }

  return out.join('\n')
}
