'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  analyzeContribution,
  renderComment,
} = require('./contribution-guidance.cjs');

test('accepts descriptive aliases for an ordinary code change', () => {
  const analysis = analyzeContribution({
    body: [
      '## Sorun',
      'Eksik parametre isteği yanlış role yazılıyordu.',
      '## Değişiklikler',
      'Prompt ve örnek düzeltildi.',
      '## Doğrulama',
      'pytest: 201 passed.',
    ].join('\n\n'),
    paths: [
      'src/tool_call_tr/generation/providers.py',
      'tests/unit/test_production_providers.py',
    ],
  });

  assert.equal(analysis.scope, 'Kod, test veya dokümantasyon katkısı');
  assert.deepEqual(analysis.suggestions, []);
});

test('uses another accepted heading when an earlier alias is empty', () => {
  const analysis = analyzeContribution({
    body: [
      '## Değişiklikler',
      '<!-- Henüz doldurulmadı -->',
      '## Sorun',
      'Katkı botunun yorumu gereğinden katıydı.',
      '## Testler',
      'node --test: geçti.',
    ].join('\n\n'),
    paths: ['.github/scripts/contribution-guidance.cjs', '.github/scripts/contribution-guidance.test.cjs'],
  });

  assert.deepEqual(analysis.suggestions, []);
});

test('accepts a concise freeform description for a documentation change', () => {
  const analysis = analyzeContribution({
    body: 'Katkı rehberindeki eski ve belirsiz açıklamaları daha açık hale getirir.',
    paths: ['CONTRIBUTING.md'],
  });

  assert.deepEqual(analysis.suggestions, []);
});

test('gives actionable non-blocking suggestions for an untested code change', () => {
  const analysis = analyzeContribution({
    body: '## Özet\n\nProvider davranışını değiştirir.',
    paths: ['src/tool_call_tr/generation/providers.py'],
  });

  assert.equal(analysis.suggestions.length, 2);
  assert.match(analysis.suggestions[0], /çalıştırılan doğrulamayı belirtin/);
  assert.match(analysis.suggestions[1], /test değişikliği görünmüyor/);
});

test('keeps source and quality guidance for dataset contributions', () => {
  const analysis = analyzeContribution({
    body: [
      '## Değişiklik',
      'Yeni dataset kayıtları ekler.',
      '## Kaynak ve lisans',
      'Uygulanamaz',
    ].join('\n\n'),
    paths: ['data/dataset/needs_revision/sample.jsonl'],
  });

  assert.equal(analysis.scope, 'Tool/veri katkısı');
  assert.equal(analysis.suggestions.length, 2);
  assert.match(analysis.suggestions[0], /yalnız `Uygulanamaz`/);
  assert.match(analysis.suggestions[1], /kalite raporu/);
});

test('accepts a sourced blueprint contribution', () => {
  const analysis = analyzeContribution({
    body: [
      '## Değişiklik',
      'Özgün bir deprem senaryosu ekler.',
      '## Kaynak ve lisans',
      'AFAD açık verisi, kullanım koşulları 10 Ağustos 2026 tarihinde kontrol edildi.',
    ].join('\n\n'),
    paths: ['blueprints/earthquake.jsonl'],
  });

  assert.deepEqual(analysis.suggestions, []);
});

test('renders visible freshness metadata and advisory language', () => {
  const body = renderComment({
    analysis: {
      scope: 'Kod, test veya dokümantasyon katkısı',
      suggestions: ['Test sonucunu belirtin.'],
    },
    guideUrl: 'https://example.test/CONTRIBUTING.md',
    checkedAt: '10 Ağustos 2026 18:45:00',
    headSha: '1234567890abcdef',
  });

  assert.match(body, /tek başına merge engeli değildir/);
  assert.match(body, /Son kontrol.*10 Ağustos 2026 18:45:00/);
  assert.match(body, /commit `1234567`/);
});
