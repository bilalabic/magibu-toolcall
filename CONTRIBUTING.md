# Katkı rehberi

Bu depo tool sözleşmesi, execution implementasyonu, scenario blueprint, dataset
kaydı, kalite kuralı ve dokümantasyon katkılarını kabul eder. Her katkı ayrı bir
branch ve GitHub pull request üzerinden ilerler. CLI içinde kullanıcı hesabı,
reviewer rolü veya onay sistemi yoktur.

## Başlamadan önce

1. Değişikliğin tek ve açık bir amacı olsun.
2. Yeni bir tool için veri kaynağını, erişim yöntemini, lisansı/kullanım
   koşullarını, güncellik sınırını ve kişisel veri riskini araştırın.
3. Function adı, parametre anahtarları, enum değerleri ve yapılandırılmış alanlar
   İngilizce kalır. Kullanıcı/asistan metinleri ile tool ve parametre açıklamaları
   doğal Türkiye Türkçesiyle yazılır.
4. Secret, gerçek kullanıcı verisi ve yeniden dağıtım izni belirsiz içerik
   repository’ye eklenmez.

## Tool katkısı

Yeni bir tool önce `registry/proposals/pilot_candidates.jsonl` içinde `candidate`
olarak tanımlanır. Kayıt şu sözleşmeleri birlikte taşır:

- kararlı `tool_id`, `tool_version`, domain ve function adı;
- JSON Schema uyumlu input ve output şemaları;
- varsayılan ve desteklenen execution türleri;
- erişim, kimlik doğrulama ve credential environment variable adları;
- kaynak, lisans, kullanım koşulu kontrol tarihi ve riskler;
- gerekiyorsa fixture kimlikleri veya salt-okunur HTTP sözleşmesi.

Başlangıç formu için [tool proposal şablonunu](docs/tool_proposal_template.md),
kesin alanlar için
[`schemas/tool_registry.schema.json`](schemas/tool_registry.schema.json) dosyasını
kullanın.

Execution implementasyonu seçilen moda göre hazırlanır:

| Mod | Katkıda bulunulacak yer | Kabul ölçütü |
| --- | --- | --- |
| `local_executable` | `src/tool_call_tr/execution/local_tools.py` ve adapter eşlemesi | Deterministik, ağsız, input/output şemalarıyla uyumlu ve testli |
| `mock` | `registry/proposals/fixtures/<fixture_id>.json` ve registry `fixture_ids` | Sabit, şema uyumlu, kaynak kökeni açık ve kişisel verisiz |
| `fully_simulated` | Stateful adapter implementasyonu | Dış sisteme dokunmayan, resetlenebilir ve durum geçişleri testli |
| `real_api` | Registry `execution.http`; gerekirse HTTP adapter geliştirmesi | Yalnız HTTPS GET, izinli host, açık auth, timeout ve şema doğrulaması |
| `sandbox` | Yeni adapter ve test paketi gerekir | Repository’de bugün çalışır sandbox adapter yoktur |

Basit bir `real_api` katkısı için tool’a özel wrapper zorunlu değildir: mevcut
HTTP adaptörü registry’deki URL, query eşlemesi, header/auth ve `response_path`
alanlarını kullanır. Kaynak özel dönüşüm gerektiriyorsa mevcut adaptör yeterli
sayılmaz; normalizasyon kodu ve testleri aynı PR’da eklenmelidir. POST, ödeme,
e-posta ve başka yan etkili canlı işlemler mevcut adaptörün kapsamı dışındadır.

En az şu testleri ekleyin:

- geçerli input için beklenen sonuç;
- geçersiz veya eksik input;
- output schema uyumu;
- execution moda özgü hata, timeout veya reset davranışı;
- gerçek API sözleşmesinde secret redaction ve izinli-host sınırı.

## Scenario blueprint katkısı

Blueprint, model üretiminden önce yazılır ve
[`schemas/scenario_blueprint.schema.json`](schemas/scenario_blueprint.schema.json)
ile doğrulanır. Yeni kayıt:

- benzersiz ve kararlı bir ID taşımalı;
- yalnız registry’de bulunan function adlarını kullanmalı;
- tool gereksinimini, verilen/eksik parametreleri ve beklenen çağrıları açıkça
  belirtmeli;
- tool sonucu ile son cevap arasındaki bağı tanımlamalı;
- yasak davranışları, kaynak türünü, domain’i, zorluk seviyesini ve execution
  ortamını içermeli;
- iç operasyon etiketlerini doğal kullanıcı/asistan metnine taşımamalıdır.

Kategori önceliği ve multi-tool kuralları için
[scenario blueprint rehberini](docs/scenario_blueprints.md) izleyin.

## Dataset katkısı

Model çıktısı doğrudan `accepted` olmaz. Aday sırasıyla şema, registry,
execution, duplicate, Türkçe/grounding kalite kontrolleri ve insan incelemesinden
geçer. İncelenecek aday dosyası
`data/dataset/needs_revision/<job_id>.pr.review.jsonl`, eşleşen kalite raporu
`review/dataset/<job_id>.pr.quality.json` adıyla PR’a eklenebilir. Nihai birleşik
dataset yalnız `data/dataset/accepted/dataset.jsonl` yolunda tutulur.

Ham kaynaklar, staging çıktıları, checkpoint’ler ve provider response’ları
üretilmiş çalışma verisidir; Git geçmişine eklenmez. Canonical kayıt ile eğitim
projeksiyonu birbirine karıştırılmaz.

## Yerel kontroller

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\magibu-toolcall.exe registry validate registry\registry.jsonl
.\.venv\Scripts\magibu-toolcall.exe registry validate registry\proposals\pilot_candidates.jsonl
.\.venv\Scripts\magibu-toolcall.exe blueprint validate blueprints\pilot_general.jsonl --registry registry\proposals\pilot_candidates.jsonl
```

Değişen bir fixture’ı ayrıca çalıştırın:

```powershell
.\.venv\Scripts\magibu-toolcall.exe tool run-fixture <fixture_id> --registry registry\proposals\pilot_candidates.jsonl
```

## Pull request ve otomatik yorum

PR şablonundaki katkı türü, değişiklik, kaynak/lisans, otomatik kontrol ve insan
incelemesi bölümlerini doldurun. `Contribution guidance` workflow’u:

- PR şablonundaki zorunlu bölümleri ve seçilen katkı türünü;
- execution/registry değişikliğiyle test ve dataset değişikliğiyle kalite raporu
  ilişkisini kontrol eder.

Bot yalnız PR açıklamasını ve değişen dosya adlarını okur; tek bir güncellenebilir
yorum üretir. Katkı dalındaki kodu çalıştırmaz, otomatik düzeltme veya onay vermez.
Registry, fixture, blueprint, dataset ve test doğrulamaları ayrı `validate`
workflow’unda; nihai karar insan incelemesindedir.
