# magibu-toolcall — teknik kullanım rehberi

[← Proje tanıtımına dön](README.md) · [Katkı rehberi](CONTRIBUTING.md)

Bu belge geliştirici kurulumu, CLI kullanımı, tool/blueprint katkısı ve dataset
üretim akışını açıklar. Aktif kapsam `original_turkish` ve `turkey_native`
dataset kayıtlarıdır. Çeviri/lokalizasyon ve benchmark üretimi ayrı tutulur ve
şu anda çalıştırılmaz.

## 1. Kurulum

Gereksinimler:

- Python 3.11+
- Git
- geliştirme için GitHub CLI isteğe bağlıdır

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Kurulumdan sonra CLI:

```powershell
.\.venv\Scripts\magibu-toolcall.exe --help
```

Dağıtım/CLI adı `magibu-toolcall`, Python import paketi `tool_call_tr`’dir.

## 2. Yapılandırma ve API anahtarları

Yerel `.env` dosyası Git tarafından yok sayılır:

```powershell
Copy-Item .env.example .env
notepad .env
```

Gerçek anahtarları tırnak, `< >` veya örnek placeholder ile sarmalamadan girin.
Anahtarları komut satırı argümanına, fixture’a, manifest’e, kalite raporuna veya
PR açıklamasına yazmayın.

Aktif üretim politikası:

- DeepSeek Flash: birincil doğal dil üretimi
- DeepSeek Pro: retry’ler tükendiğinde fallback
- OpenAI mini model: birincil yapılandırılmış kalite değerlendirmesi
- OpenAI tam model: non-pass kayıtlar ve belirlenen pass örneklemi için escalation
- OpenAI embedding modeli: semantic duplicate taraması

Model kimlikleri ve bütçeler `.env.example` içinde örneklenir; etkili yapılandırma
secret göstermeden şu komutla okunur:

```powershell
.\.venv\Scripts\magibu-toolcall.exe config
```

Provider erişimini yalnız açık canlı onayla sınayın:

```powershell
.\.venv\Scripts\magibu-toolcall.exe provider check --provider all --confirm-live --output json
```

Bu komut model listeleme uçlarını kontrol eder; dataset üretmez. Provider kota ve
maliyet bilgisinin doğruluk kaynağı provider dashboard’udur.

## 3. Repository sözleşmeleri

| Varlık | Kaynak | Doğrulama |
| --- | --- | --- |
| Tool registry | `schemas/tool_registry.schema.json` | Şema, ID/function/domain, semver, execution ve HTTP kuralları |
| Fixture | Registry input/output şemaları | Function, argüman, sonuç ve `fixture_ids` bağlantısı |
| Blueprint | `schemas/scenario_blueprint.schema.json` | Kategori, tool seçimi, çağrı sırası ve beklenen davranış |
| Dataset | `schemas/dataset.schema.json` | Mesaj, tool call/result, provenance, execution, kalite ve review |
| Batch job | `schemas/job_manifest.schema.json` | Input/registry checksum, shard, checkpoint, bütçe ve dağılım |

Machine alanları İngilizce ve kararlı kalır. Kullanıcı/asistan metinleri ile tool
ve parametre açıklamaları Türkiye Türkçesiyle yazılır.

Kanonik registry yalnız `demo` kayıtları içerir. Pilot tool’lar
`registry/proposals/pilot_candidates.jsonl` içinde `candidate` durumundadır.
`candidate`, canlı kaynak veya lisans onayı değildir.

## 4. Tool katkısı ve execution

Ayrıntılı katkı sözleşmesi [CONTRIBUTING.md](CONTRIBUTING.md) içindedir. Temel
doğrulama ve smoke testi:

```powershell
.\.venv\Scripts\magibu-toolcall.exe registry validate registry\proposals\pilot_candidates.jsonl
.\.venv\Scripts\magibu-toolcall.exe tool run-fixture calculator.evaluate.basic --registry registry\proposals\pilot_candidates.jsonl
.\.venv\Scripts\magibu-toolcall.exe tool run-fixture calendar.create_event.confirmed --registry registry\proposals\pilot_candidates.jsonl
```

Mevcut proposal dağılımı 4 `local_executable`, 14 `mock` ve 2
`fully_simulated` tool’dur.

### Execution kuralları

- `local_executable`: ağsız ve deterministik fonksiyon; implementasyon
  `execution/local_tools.py` ve adapter eşlemesinde bulunur.
- `mock`: registry’de tanımlı, input/output şemalarından geçen fixture.
- `fully_simulated`: dış sisteme dokunmayan ve `reset()` ile başlangıç durumuna
  dönen stateful adapter.
- `real_api`: yalnız onaylı, salt-okunur HTTPS GET JSON sözleşmesi.
- `sandbox`: şemada tanımlıdır fakat repository’de çalışır adapter yoktur.

Router istenen mod dışında başka moda sessizce düşmez. Mod değişimi açık neden ve
transformation history olayı gerektirir. Normalize edilen execution durumları
`not_called`, `passed`, `failed`, `timeout`, `rate_limited`, `empty_result` ve
`invalid_result` değerleridir.

Basit canlı GET kaynakları registry’deki `execution.http` alanıyla çalışır;
tool’a özel wrapper zorunlu değildir. Özel response dönüşümü gerekiyorsa adapter
geliştirmesi ve testleri eklenmeden tool çalışır kabul edilmez. `tool run-api`
yalnız canonical registry’deki `approved` read-only tool için ve
`--confirm-live` ile kullanılabilir; bugün böyle bir kayıt yoktur.

## 5. Blueprint hazırlama

Blueprint model çağrısından önce yazılır. Beş ana kategori vardır:

1. `multi_tool`
2. `multi_turn`
3. `missing_parameter`
4. `no_tool`
5. `single_tool`

Bu sıra kategori önceliğidir. İki veya daha fazla çağrı `multi_tool` sayılır;
parallel/sequential davranış secondary tag ve execution order ile tutarlı
olmalıdır.

```powershell
.\.venv\Scripts\magibu-toolcall.exe blueprint validate blueprints\pilot_general.jsonl --registry registry\proposals\pilot_candidates.jsonl
.\.venv\Scripts\magibu-toolcall.exe blueprint validate blueprints\pilot_turkey_native.jsonl --registry registry\proposals\pilot_candidates.jsonl
```

Repository geneli için daha güçlü kontrol:

```powershell
.\.venv\Scripts\python.exe scripts\check_repository_contributions.py
```

Bu kontrol iki registry’yi, bütün fixture bağlantılarını, sonuç şemalarını, bütün
blueprint dosyalarını ve dosyalar arası yinelenen blueprint ID’lerini denetler.

## 6. Tek kayıtla uçtan uca CLI testi

Tek kayıtlık regresyon blueprint’i güvenli bir smoke test sağlar.

### 6.1 Provider ve sözleşme kontrolü

```powershell
.\.venv\Scripts\magibu-toolcall.exe provider check --provider all --confirm-live --output json
.\.venv\Scripts\magibu-toolcall.exe blueprint validate blueprints\regressions\parcel_natural_v2.jsonl --registry registry\proposals\pilot_candidates.jsonl
```

İlk komut canlıdır; ikinci komut tamamen yereldir.

### 6.2 Aday üretimi

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset generate blueprints\regressions\parcel_natural_v2.jsonl `
  --registry registry\proposals\pilot_candidates.jsonl `
  --job-id dataset-smoke-001 `
  --output data\dataset\staging\dataset-smoke-001.jsonl `
  --start-number 1 `
  --max-workers 1 `
  --token-budget 20000 `
  --execute-live
```

Komut blueprint ve registry checksum’larını sabitler; manifest, checkpoint ve
çalışma kanıtlarını `runs/dataset/dataset-smoke-001/` altında tutar. Üretilen
kayıt otomatik olarak insan onaylı sayılmaz.

### 6.3 Dataset doğrulaması

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset validate data\dataset\staging\dataset-smoke-001.jsonl --output json
```

### 6.4 Execution, duplicate ve OpenAI kalite kontrolü

Accepted referans dosyası henüz yoksa `--reference` vermeyin:

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset quality `
  data\dataset\staging\dataset-smoke-001.jsonl `
  data\dataset\needs_revision\dataset-smoke-001.pr.review.jsonl `
  --registry registry\proposals\pilot_candidates.jsonl `
  --semantic-provider openai `
  --semantic-threshold 0.90 `
  --semantic-cache .cache\semantic `
  --judge-provider openai `
  --judge-escalation `
  --judge-escalation-sample-rate 0.10 `
  --judge-max-workers 1 `
  --confirm-live `
  --report review\dataset\dataset-smoke-001.pr.quality.json
```

Accepted dataset oluştuğunda komuta şu seçenek eklenir:

```text
--reference data/dataset/accepted/dataset.jsonl
```

Kalite komutu execution ve otomatik değerlendirme kanıtını yeniden hesaplar;
insan onayı vermez. `.pr.review.jsonl` adayını ve eşleşen `.pr.quality.json` raporunu
GitHub PR’a ekleyin. Bütün otomatik kapılar geçtiğinde kaydın önerilen yaşam
döngüsü durumu `accepted` yapılabilir; karar ancak branch protection altındaki
PR onayı ve merge ile repository açısından geçerli olur.

## 7. Toplu üretim

Normal başlangıç komutu `dataset generate`’dır. Ayrı `batch plan/run` komutları
yalnız önceden planlanmış işi devam ettirmek veya özel shard yönetmek içindir.

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset generate blueprints\pilot_general.jsonl `
  --registry registry\proposals\pilot_candidates.jsonl `
  --job-id general-pilot-v1 `
  --max-workers 4 `
  --token-budget 250000 `
  --execute-live
```

`--output` verilmezse kayıtlar `data/dataset/staging/<job_id>.jsonl` yoluna,
manifest/checkpoint/error kanıtları `runs/dataset/<job_id>/` yoluna yazılır.
`--registry` yolu ve checksum’ı manifeste bağlanır. ID aralığı için
`--start-number`, mevcut kayıt çakışması için birden fazla `--existing`, dağılım
hedefleri için `--targets` kullanılabilir.

Durum ve dağılım raporu:

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset batch status runs\dataset\general-pilot-v1\manifest.json --output json
.\.venv\Scripts\magibu-toolcall.exe dataset batch report runs\dataset\general-pilot-v1\manifest.json --output json
```

1.000 kayıt tek kontrolsüz çağrı olarak üretilmemelidir. Önerilen kapılar 30, 100
ve 250 kayıttır; her kapıda hata türleri, tool/kategori/kaynak dağılımı, duplicate
oranı, insan inceleme uyumu, token kullanımı ve provider maliyeti değerlendirilir.

## 8. GitHub katkı kontrolü

İki farklı workflow farklı güvenlik görevleri taşır:

- `Pull request validation`, PR branch’ini checkout eder ve testleri çalıştırır;
  token yetkisi salt okunurdur.
- `Contribution review`, güvenilir base revision’ı çalıştırır. PR blob’larını
  yalnız veri olarak indirir, katkı kodunu çalıştırmaz ve tek bir güncellenebilir
  yorum bırakır.

Katkı botu danışman niteliğindedir. Şema değişiklikleri base şemayla güvenli
biçimde değerlendirilemeyeceği için ayrıca normal CI ve insan incelemesi ister.
Reviewer kimliği, yorumlar, onay ve change-request geçmişi GitHub’da tutulur.

`pull_request_target` workflow’u yalnız default branch’teki workflow tanımıyla
çalışır. Bu nedenle workflow’u ilk kez ekleyen PR’da yalnız normal `validate`
kontrolü görülür; otomatik PR yorumu değişiklik `main` ile birleştirildikten sonra
açılan veya güncellenen sonraki PR’larda devreye girer.

Önerilen `main` ruleset ayarları:

- pull request zorunluluğu;
- en az bir bağımsız onay;
- yeni commit’te eski onayların düşürülmesi;
- konuşmaların çözülmesi;
- `validate` durum kontrolünün zorunlu olması;
- doğrudan push ve force-push’ın kapatılması.

## 9. Gerçek API’ye geçiş

Bir mock veya snapshot kaynağını canlı API’ye taşımadan önce:

1. Resmî dokümantasyon, kullanım koşulu, lisans, kota ve auth yöntemi doğrulanır.
2. Tool’un salt-okunur ve kişisel verisiz sınırı yazılır.
3. Input/output şemaları sağlayıcı biçiminden bağımsız tutulur.
4. Gerekirse response normalizasyonu eklenir.
5. Credential yalnız environment variable adıyla registry’ye yazılır.
6. Timeout, rate-limit, boş ve geçersiz sonuç testleri eklenir.
7. Canlı sonuç dataset kanıtı olacaksa izinli snapshot alınır; kaynak, zaman,
   sürüm ve checksum ile dondurulur.
8. Registry kaydı ve lifecycle değişikliği PR incelemesinden geçer.

Zamanla değişen canlı sonuç, geçmiş bir dataset kaydının tekrar doğrulama temeli
olarak kullanılmaz. Dataset için dondurulmuş kanıt tercih edilir.

## 10. Export

Canonical accepted kayıtlar:

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset export approved-records.jsonl data\dataset\accepted\dataset.jsonl
```

Eğitim sistemine verilecek metadata’sız görünüm:

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset export data\dataset\accepted\dataset.jsonl data\dataset\training\dataset.jsonl --projection training
```

Training projection yalnız `id`, `messages` ve `tools` alanlarını içerir.
Canonical dosya provenance, execution ve kalite kanıtlarını korur.

## 11. Askıdaki alanlar

xLAM/When2Call import-lokalizasyon komutları ve benchmark namespace’i kodda
mevcuttur; aktif dataset üretim prosedürüne dahil değildir. Yeniden açıldıklarında
kaynak kullanım koşulları, ayrı review planı ve benchmark kontaminasyon/freeze
kapıları onaylanmadan çalıştırılmamalıdır.

Benchmark yaşam döngüsü için [ayrı belgeye](data/benchmark/README.md) bakın.

## 12. Dizinler ve Git politikası

```text
blueprints/                         İzlenen blueprint ve regresyonlar
registry/                           Canonical registry ve fixture’lar
registry/proposals/                 Candidate tool paketleri
data/dataset/staging/               Yerel üretilmiş adaylar
data/dataset/needs_revision/        PR’a seçilerek eklenen review adayları
data/dataset/accepted/dataset.jsonl Canonical accepted dataset
review/dataset/                     PR’a seçilerek eklenen kalite raporları
runs/dataset/                       Yerel manifest/checkpoint/provider kanıtları
schemas/                            JSON Schema sözleşmeleri
```

`.gitignore` ham, staging, run ve genel üretilmiş çıktıları dışarıda bırakır.
Yalnız `<job_id>.pr.review.jsonl`, `<job_id>.pr.quality.json` ve canonical
`accepted/dataset.jsonl` açıkça review edilebilir yollar olarak izlenebilir.

## 13. Son doğrulama

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\check_repository_contributions.py
git status --short
```

Testlerin geçmesi, canlı kaynakların lisans veya veri kalitesi onayı anlamına
gelmez; bu kararlar PR kanıtı ve insan incelemesi gerektirir.
