# Katkı rehberi

[← Proje tanıtımı](README.md) · [Dokümantasyon merkezi](docs/README.md)

Bu depo tool sözleşmesi, execution implementasyonu, scenario blueprint, dataset
kaydı, kalite kuralı, test ve dokümantasyon katkılarını kabul eder. Her katkı
ayrı bir branch ve GitHub pull request üzerinden ilerler. CLI içinde kullanıcı
hesabı, reviewer rolü veya onay sistemi yoktur; kimlik ve karar geçmişinin kaynağı
GitHub'dır.

## Başlamadan önce

1. Değişikliğin tek ve açık bir amacı olsun.
2. Yeni bir tool için veri kaynağını, erişim yöntemini, lisansı/kullanım
   koşullarını, güncellik sınırını ve kişisel veri riskini araştırın.
3. Function adı, parametre anahtarları, enum değerleri ve yapılandırılmış alanlar
   İngilizce kalır. Kullanıcı/asistan metinleri ile tool ve parametre açıklamaları
   doğal Türkiye Türkçesiyle yazılır.
4. Secret, gerçek kullanıcı verisi ve yeniden dağıtım izni belirsiz içerik
   repository'ye eklenmez.

Katkı paketinin beklenen asgari içeriği:

| Katkı türü | Aynı PR'da beklenenler |
| --- | --- |
| Tool | Registry kaydı, seçilen moda uygun execution/fixture, kaynak kanıtı ve test |
| Blueprint | Geçerli blueprint, registry bağlantısı ve gerekiyorsa regresyon testi |
| Dataset | İnceleme adayı, aynı `job_id` değerli kalite raporu ve provenance |
| Kod/kalite kuralı | Uygulama değişikliği, olumlu/olumsuz testler ve güncel belge |
| Dokümantasyon | Gerçek komut ve davranışla uyumlu açıklama; kaynak varsa bağlantı |

## Tool katkısı

Yeni tool kayıtları `registry/proposals/` altında katkıya özel bir `.jsonl`
dosyasında `candidate` olarak tanımlanır. Dosya adı içeriği açıklayan
`<domain>_<source>.jsonl` düzenini izler; örneğin
`registry/proposals/earthquake_afad.jsonl`. Ortak bir `registry.jsonl` proposal
dosyasını düzenlemeyin; bu kural paralel PR'larda çakışmayı önler. Kayıt şu
sözleşmeleri birlikte taşır:

- Her katkı veya paket, üst dizinde kendine ait ve açıklayıcı adlı tek bir
  registry parçasını düzenler.
- Yalnız `.jsonl` kullanılır; `.json` proposal dosyası kabul edilmez.
- Her satır tam olarak bir registry kaydı içerir. Bir paket aynı dosyada birden
  fazla tool bulundurabilir; JSON dizi biçimi kullanılmaz.
- Birleştirilmiş proposal registry dosyası üretilse bile Git'e eklenmez.
- `registry validate registry/proposals` komutu bütün parçaları birlikte kontrol
  eder ve dosyalar arasındaki tekrarları reddeder.

- kararlı `tool_id`, `tool_version`, domain ve function adı;
- JSON Schema uyumlu input ve output şemaları;
- varsayılan ve desteklenen execution türleri;
- erişim, kimlik doğrulama ve credential environment variable adları;
- kaynak, lisans, kullanım koşulu kontrol tarihi ve riskler;
- gerekiyorsa fixture kimlikleri veya salt-okunur HTTP sözleşmesi.

Bir tool'un input ve output şemaları registry kaydının **içinde** yaşar:
`function.parameters` ve `output_schema`. `schemas/` dizini yalnız meta-şemaları
tutar; tool başına ayrı şema dosyası açılmaz. Kayıt sözleşmesi
`additionalProperties: false` olduğu için harici bir şemaya referans verilecek
alan zaten yoktur.

Şema doğrulamasının geçmesi kaynak, lisans veya canlı kullanım onayı değildir.
Bu kararlar PR'daki kaynak kanıtı ve insan incelemesiyle verilir.

Başlangıç formu için [tool proposal şablonunu](docs/tool_proposal_template.md),
kesin alanlar için
[`schemas/tool_registry.schema.json`](schemas/tool_registry.schema.json) dosyasını
kullanın.

Execution implementasyonu seçilen moda göre hazırlanır:

| Mod | Katkıda bulunulacak yer | Kabul ölçütü |
| --- | --- | --- |
| `local_executable` | `src/tool_call_tr/execution/local/<domain>_<source>.py` içinde modül düzeyinde `FUNCTIONS` sözlüğü | Deterministik, ağsız, input/output şemalarıyla uyumlu ve testli |
| `mock` | `registry/proposals/fixtures/<fixture_id>.json` ve registry `fixture_ids` | Sabit, şema uyumlu, kaynak kökeni açık ve kişisel verisiz |
| `fully_simulated` | `src/tool_call_tr/execution/simulation/<domain>_<source>.py` içinde modül düzeyinde `TOOLS` dizisi | Dış sisteme dokunmayan, resetlenebilir ve durum geçişleri testli |
| `real_api` | Registry `execution.http`; gerekirse HTTP adapter geliştirmesi | Yalnız HTTPS GET, izinli host, açık auth, timeout ve şema doğrulaması |
| `sandbox` | Yeni adapter ve test paketi gerekir | Repository’de bugün çalışır sandbox adapter yoktur |

Hiçbir mod `src/tool_call_tr/execution/adapters.py` dosyasının düzenlenmesini
gerektirmez. Registry ve blueprint parçalarında olduğu gibi, her katkı paketi
ortak bir üst dizinde kendine ait tek bir `<domain>_<source>` dosyasını açar;
paralel PR'lar bu sayede çakışmaz. Her modun dosya düzeni, arayüzü, hata
kodları ve doğrulama komutu
[execution ortamları belgesinde](docs/execution_environments.md) tek kaynak
olarak tutulur.

Resmî yayımlanmış veriye dayanan bir `local_executable` tool'u, veriyi
`data/snapshots/<snapshot_version>/` altında sürümlenmiş bir snapshot olarak
sabitler. Ham dosya başına `sha256` zorunludur; beyan edilen bayt ile commit
edilen bayt her PR'da karşılaştırılır. Ham kaynaktan üretilmiş dosyaya giden
dönüşüm `scripts/snapshots/<domain>_<source>.py` altında commit edilir ve
deterministik olmalıdır. Alan listesi ve doğrulama komutu yine execution
ortamları belgesindedir.

Basit bir `real_api` katkısı için tool’a özel wrapper zorunlu değildir: mevcut
HTTP adaptörü registry’deki URL, query eşlemesi, header/auth ve `response_path`
alanlarını kullanır. Kaynak özel dönüşüm gerektiriyorsa mevcut adaptör yeterli
sayılmaz; normalizasyon kodu ve testleri aynı PR’da eklenmelidir. POST, ödeme,
e-posta ve başka yan etkili canlı işlemler mevcut adaptörün kapsamı dışındadır.

Paketler paralel yazıldığı için çıktı şekilleri de sözleşmelidir. Kaynak künyesi
(`source` nesnesi), birim alanı, tarih ve para birimi biçimleri, boş sonuç
davranışı ve mevcut bir domain'e eklenen aracın sınırı
[execution ortamları belgesindeki çıktı konvansiyonlarında](docs/execution_environments.md)
tanımlıdır. Kimseyle koordinasyon gerekmez; o bölümü okumak koordinasyonun
kendisidir.

Halihazırda aracı bulunan bir domain'e yeni araç ekliyorsanız, iki aracın sınırını
tool açıklamalarında belirtin ve PR'da tek cümleyle yazın. Aynı soruya iki aracın
da makul göründüğü durum, modele tahmin etmeyi öğretir.

Katkılar `pyproject.toml` dosyasını düzenlemez. Dönüştürme scriptleri gerektirdiği
paketi kendi docstring'inde belirtir; test paketine gerçekten yeni bir bağımlılık
gerekiyorsa önce PR'da sorun, karar
[bağımlılık kararlarına](docs/dependency_decisions.md) yazılır.

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

Repository'ye eklenen blueprint katkıları da yalnız `.jsonl` kullanır ve her
satırda bir blueprint kaydı taşır. Dosya adı registry parçasıyla aynı
`<domain>_<source>.jsonl` düzenini izler. `tests/fixtures/` altındaki tekil
`.json` dosyaları yalnız test verisidir; katkı formatına örnek değildir.

Kategori önceliği ve multi-tool kuralları için
[scenario blueprint rehberini](docs/scenario_blueprints.md) izleyin.

## Dataset katkısı

Model çıktısı doğrudan `accepted` olmaz. Aday sırasıyla şema, registry,
execution, duplicate, Türkçe/grounding kalite kontrolleri ve insan incelemesinden
geçer. Otomatik kalite komutu language ve review alanlarına insan onayı yazmaz.
İncelenecek aday dosyası
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
```

Bir proposal registry parçası veya blueprint eklediyseniz proposal klasörünü ve
kendi blueprint yolunuzu vererek ayrıca doğrulayın:

```powershell
$ProposalRegistry = "registry\proposals"
$BlueprintFile = "blueprints\contribution.jsonl"
$FixtureId = "your.fixture.id"
.\.venv\Scripts\magibu-toolcall.exe registry validate $ProposalRegistry
.\.venv\Scripts\magibu-toolcall.exe blueprint validate $BlueprintFile --registry $ProposalRegistry
.\.venv\Scripts\magibu-toolcall.exe tool run-fixture $FixtureId --registry $ProposalRegistry
```

Snapshot eklediyseniz ayrıca çalıştırın; aynı kontrol CI'da da yapılır:

```powershell
.\.venv\Scripts\python.exe -m tool_call_tr.snapshots data\snapshots
```

## Pull request ve otomatik yorum

Önerilen PR şablonu değişiklik, doğrulama ve gerektiğinde kaynak-lisans olmak
üzere üç kısa bölümden oluşur. Her PR'da değişikliği ve çalıştırılan doğrulamaları
açıkça belirtin. Bot
`Değişiklik`, `Değişiklikler`, `Sorun ve çözüm`, `Özet`, `Doğrulama`, `Testler`
gibi eş anlamlı başlıkları kabul eder; kod, test ve dokümantasyon PR'larını tam
şablonu kullanmaya zorlamaz. Tool, fixture, blueprint veya dataset katkılarında
kaynak ve lisans açıklaması gerekir. İnsan incelemesini reviewer GitHub PR
üzerinden yapar.
`Contribution guidance` workflow'u:

- değişiklik açıklamasını ve kod değişikliklerinde doğrulama bilgisini;
- kod değişikliğiyle test, tool/veri katkısıyla kaynak-lisans ve dataset
  değişikliğiyle kalite raporu ilişkisini kontrol eder.

Bot yalnız PR açıklamasını ve değişen dosya adlarını okur; tek bir güncellenebilir
yorum üretir. Öneriler açıklayıcıdır ve tek başına merge engeli değildir. Yorumun
GitHub'daki oluşturulma zamanı değişmediği için bot, son kontrol zamanını ve commit
kimliğini yorumun içinde ayrıca gösterir. Katkı dalındaki kodu çalıştırmaz,
otomatik düzeltme veya onay vermez. Registry, fixture, blueprint, dataset ve test
doğrulamaları ayrı `validate` workflow'unda; nihai karar insan incelemesindedir.
