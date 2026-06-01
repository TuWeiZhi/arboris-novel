import type { AdvancedGenerateVariant, ChapterVersion } from '@/api/novel'

const CONTENT_KEYS = [
  'content',
  'chapter_content',
  'chapter_text',
  'full_content',
  'text',
  'body',
  'story',
] as const

function extractChapterText(value: unknown): string | null {
  if (!value) {
    return null
  }

  if (typeof value === 'string') {
    return value
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const nested = extractChapterText(item)
      if (nested) {
        return nested
      }
    }
    return null
  }

  if (typeof value === 'object') {
    for (const key of CONTENT_KEYS) {
      const nested = extractChapterText((value as Record<string, unknown>)[key])
      if (nested) {
        return nested
      }
    }
  }

  return null
}

export function normalizeChapterContent(content: string | null | undefined): string {
  if (!content) {
    return ''
  }

  let normalized = content

  try {
    const parsed = JSON.parse(content)
    const extracted = extractChapterText(parsed)
    if (extracted) {
      normalized = extracted
    }
  } catch {
    // 保持原始字符串
  }

  const unquoted = normalized.replace(/^"|"$/g, '')
  return unquoted
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\')
}

export function normalizeChapterVersions(
  versions: Array<string | ChapterVersion> | null | undefined,
): ChapterVersion[] {
  if (!Array.isArray(versions)) {
    return []
  }

  return versions.map((version) => {
    if (typeof version === 'string') {
      return {
        id: 0,
        content: normalizeChapterContent(version),
        style: '标准',
        metadata: null,
        is_selected: false,
      }
    }

    return {
      ...version,
      content: normalizeChapterContent(version.content),
      style: version.style || '标准',
      metadata: version.metadata || null,
      is_selected: Boolean(version.is_selected),
    }
  })
}

export function buildVersionsFromVariants(variants: AdvancedGenerateVariant[] | null | undefined): ChapterVersion[] {
  if (!Array.isArray(variants)) {
    return []
  }

  return variants.map((variant) => ({
    id: variant.version_id,
    content: normalizeChapterContent(variant.content),
    style: variant.metadata?.style_hint || `v${variant.index + 1}`,
    metadata: variant.metadata || null,
    is_selected: false,
  }))
}

export function estimateChapterWordCount(content: string | null | undefined): number {
  return normalizeChapterContent(content).replace(/\s/g, '').length
}
