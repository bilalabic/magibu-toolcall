'use strict';

const MARKER = '<!-- magibu-contribution-guidance -->';

const SECTION_ALIASES = {
  change: [
    'değişiklik',
    'değişiklikler',
    'sorun',
    'sorun ve çözüm',
    'özet',
    'açıklama',
    'change',
    'changes',
    'summary',
    'problem',
    'what changed',
  ],
  source: [
    'kaynak ve lisans',
    'kaynak/lisans',
    'kaynak',
    'lisans',
    'source and license',
    'source',
    'license',
  ],
  validation: [
    'otomatik kontroller',
    'doğrulama',
    'doğrulamalar',
    'test',
    'testler',
    'validation',
    'checks',
    'tests',
  ],
};

function normalizeHeading(value) {
  return value.trim().toLocaleLowerCase('tr-TR').replace(/\s+/g, ' ');
}

function parseSections(body) {
  const headings = [...body.matchAll(/^##\s+(.+?)\s*$/gm)];
  const sections = new Map();
  for (let index = 0; index < headings.length; index += 1) {
    const start = headings[index].index + headings[index][0].length;
    const end = index + 1 < headings.length ? headings[index + 1].index : body.length;
    sections.set(normalizeHeading(headings[index][1]), body.slice(start, end).trim());
  }
  return sections;
}

function cleanSection(value) {
  return (value || '')
    .replace(/<!--.*?-->/gs, '')
    .replace(/^- \[[ xX]\].*$/gm, '')
    .trim();
}

function sectionValue(sections, aliases) {
  for (const alias of aliases) {
    const value = sections.get(normalizeHeading(alias));
    if (value !== undefined) {
      const cleaned = cleanSection(value);
      if (cleaned) {
        return cleaned;
      }
    }
  }
  return '';
}

function hasMeaningfulFreeformBody(body, sections) {
  if (sections.size > 0) {
    return false;
  }
  return cleanSection(body).replace(/^#+\s+.*$/gm, '').trim().length >= 20;
}

function isTestPath(path) {
  return path.startsWith('tests/') || /(?:^|\/)[^/]+\.(?:test|spec)\.(?:c?js|mjs|ts)$/.test(path);
}

function isToolOrDataArtifact(path) {
  return (
    (/^registry\/.+\.(?:json|jsonl)$/.test(path)) ||
    (/^blueprints\/.+\.(?:json|jsonl)$/.test(path)) ||
    (/^data\/(?:dataset|benchmark)\/.+\.(?:json|jsonl)$/.test(path))
  );
}

function analyzeContribution({ body = '', paths = [] }) {
  const sections = parseSections(body);
  const suggestions = [];
  const changeValue = sectionValue(sections, SECTION_ALIASES.change);
  const validationValue = sectionValue(sections, SECTION_ALIASES.validation);
  const sourceValue = sectionValue(sections, SECTION_ALIASES.source);

  const codeChanged = paths.some(path =>
    path.startsWith('src/') ||
    path.startsWith('scripts/') ||
    path.startsWith('.github/workflows/') ||
    path.startsWith('.github/scripts/')
  );
  const testsChanged = paths.some(isTestPath);
  const toolOrDataChanged = paths.some(isToolOrDataArtifact);
  const datasetChanged = paths.some(path => /^data\/dataset\/.+\.(?:json|jsonl)$/.test(path));
  const qualityReportChanged = paths.some(path =>
    path.startsWith('review/dataset/') && path.endsWith('.pr.quality.json')
  );

  if (!changeValue && !hasMeaningfulFreeformBody(body, sections)) {
    suggestions.push(
      'Değişikliği ve nedenini kısa bir bölümde açıklayın; `Değişiklik`, `Sorun ve çözüm` veya `Özet` başlıklarından biri kullanılabilir.',
    );
  }

  const bodyMentionsValidation = /\b(?:pytest|test(?:ler)?|doğrulama|validate|checks?)\b/i.test(body);
  if (codeChanged && !validationValue && !bodyMentionsValidation) {
    suggestions.push(
      'Kod veya otomasyon değişikliği için çalıştırılan doğrulamayı belirtin; örneğin `python -m pytest: 201 passed`.',
    );
  }
  if (codeChanged && !testsChanged) {
    suggestions.push(
      'Kod veya otomasyon değişmiş ancak test değişikliği görünmüyor; mevcut testlerin neden yeterli olduğunu açıklayın ya da regression testi ekleyin.',
    );
  }

  if (toolOrDataChanged && !sourceValue) {
    suggestions.push(
      'Tool/veri paketi değişikliği algılandı. Kaynak bağlantısını, kullanım koşulunu ve kontrol tarihini yazın; harici kaynak yoksa bunu ve lisans durumunu açıklayın.',
    );
  } else if (toolOrDataChanged && /^(?:uygulanamaz|n\/?a|not applicable)[.!]?$/i.test(sourceValue)) {
    suggestions.push(
      'Tool/veri paketi için yalnız `Uygulanamaz` yazmak yeterli değildir; harici kaynak kullanılmadığını ve katkının lisans durumunu açıkça belirtin.',
    );
  }

  if (datasetChanged && !qualityReportChanged) {
    suggestions.push(
      'Dataset değişikliği var ancak eşleşen `review/dataset/*.pr.quality.json` kalite raporu görünmüyor.',
    );
  }

  return {
    scope: toolOrDataChanged ? 'Tool/veri katkısı' : 'Kod, test veya dokümantasyon katkısı',
    suggestions,
  };
}

function renderComment({ analysis, guideUrl, checkedAt, headSha }) {
  const lines = [MARKER, '## Magibu katkı rehberi', ''];
  if (analysis.suggestions.length === 0) {
    lines.push('✅ Otomatik ön kontrol tamamlandı. Merge kararı insan incelemesindedir.');
  } else {
    lines.push(
      `⚠️ ${analysis.suggestions.length} iyileştirme önerisi var. Bunlar tek başına merge engeli değildir.`,
      '',
      '### Öneriler',
      '',
      ...analysis.suggestions.map(item => `- ${item}`),
    );
  }
  lines.push(
    '',
    `**Algılanan kapsam:** ${analysis.scope}`,
    `**Son kontrol:** ${checkedAt} · commit \`${headSha.slice(0, 7)}\``,
    '',
    `> Ayrıntılar: [Katkı rehberi](${guideUrl}). Deterministik doğrulamalar ayrı \`validate\` kontrolünde çalışır; nihai kabul insan incelemesindedir.`,
  );
  return `${lines.join('\n')}\n`;
}

module.exports = {
  MARKER,
  analyzeContribution,
  parseSections,
  renderComment,
};
