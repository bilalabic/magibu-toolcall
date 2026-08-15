# magibu-toolcall — teknik kullanım rehberi

[← Proje tanıtımına dön](README.md) · [Dokümantasyon merkezi](docs/README.md) ·
[Katkı rehberi](CONTRIBUTING.md)

Bu belge kurulabilir ve çalıştırılabilir CLI akışının teknik başvuru kaynağıdır.
Mimari kararlar, kavramsal açıklamalar ve proje durumu burada tekrarlanmaz;
[dokümantasyon merkezindeki](docs/README.md) ilgili belgelere yönlendirilir.
`original_turkish` ve `turkey_native` akışları desteklenir. Repository'ye eklenen
proposal registry ve blueprint katkıları yalnız `.jsonl` kullanır; her satır bir
kayıttır. Tekil `.json` dosyaları yalnız test fixture'larında kullanılabilir.

Rehberi ilk kez kullanıyorsanız şu sırayı izleyin:

1. Kurulumu tamamlayıp yerel testleri çalıştırın.
2. Registry ve blueprint sözleşmelerini doğrulayın.
3. Önce tek kayıtlık smoke testi yürütün.
4. Üretim çıktısını otomatik kalite kontrolünden geçirin.
5. Aday kayıt ve kalite raporunu GitHub PR üzerinden insan incelemesine sunun.
6. Tek kayıt akışı doğrulandıktan sonra toplu üretime geçin.

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

Varsayılan provider rolleri:

- DeepSeek Flash: birincil doğal dil üretimi
- DeepSeek Pro: Flash üretimi retry sonrasında veya retry edilmeyen bir
  üretim/politika hatasıyla başarısız olduğunda fallback
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

Bu komut model listeleme uçlarını kontrol eder; dataset üretmez ve modelin belirli
bir prompt'a kaliteli cevap vereceğini kanıtlamaz. Kota, ücret ve kullanım
koşulları için doğruluk kaynağı provider dashboard'udur.

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

Kanonik registry yalnız altyapı testlerinde kullanılan `demo` kayıtlarını içerir.
Yeni tool’lar `registry/proposals/` altında katkıya özel `.jsonl` parçaları olarak
`candidate` durumunda eklenir. Ortak bir proposal registry
dosyası commit edilmez; CLI parçaları birlikte doğrular. `candidate`, canlı
kaynak veya lisans onayı değildir.

## 4. Tool katkısı ve execution

Ayrıntılı katkı sözleşmesi [CONTRIBUTING.md](CONTRIBUTING.md) içindedir. Temel
doğrulama ve smoke testi:

```powershell
.\.venv\Scripts\magibu-toolcall.exe registry validate registry\registry.jsonl
.\.venv\Scripts\magibu-toolcall.exe tool run-fixture utility.add.basic
```

Bu komutlar yalnız demo altyapısını sınar. Yeni proposal fixture'ı için aynı
komutlara `--registry registry\proposals` eklenir. Modların
sözleşmeleri, status değerleri ve fallback kuralları
[execution ortamları belgesinde](docs/execution_environments.md) tutulur. CLI
hiçbir execution modunu sessizce başka moda düşürmez. `tool run-api` yalnız
read-only tool için ve `--confirm-live` ile çalışır; varsayılan olarak canonical
registry'deki `approved` kayıtlarla sınırlıdır. `--registry` bir JSONL dosyası
veya parça dizini alır; `--allow-candidate` kapıyı yalnız `candidate` yaşam
döngüsüne açar, `demo` ve `deprecated` kapalı kalır ve `--confirm-live` yine
gerekir. Bugün ne `approved` bir kayıt ne de `real_api` sözleşmesi taşıyan bir
`candidate` kayıt vardır.

## 5. Blueprint hazırlama

Blueprint model çağrısından önce yazılır. Alanların anlamı, beş kategori ve
öncelik kuralları [scenario blueprint rehberinde](docs/scenario_blueprints.md)
tutulur. Bu bölüm yalnız doğrulama komutlarını gösterir.

```powershell
.\.venv\Scripts\magibu-toolcall.exe blueprint validate tests\fixtures\blueprints\valid\single_tool.json --registry registry\registry.jsonl
```

Proposal ve production blueprint dosyaları eklendikten sonra:

```powershell
$ProposalRegistry = "registry\proposals"
$BlueprintFile = "blueprints\<domain>_<source>.jsonl"
.\.venv\Scripts\magibu-toolcall.exe registry validate $ProposalRegistry
.\.venv\Scripts\magibu-toolcall.exe blueprint validate $BlueprintFile --registry $ProposalRegistry
```

Canonical registry ve tüm test paketi birlikte çalıştırılabilir:

```powershell
.\.venv\Scripts\magibu-toolcall.exe registry validate registry\registry.jsonl
.\.venv\Scripts\python.exe -m pytest
```

Test paketi fixture execution’larını, örnek blueprint kategorilerini ve
repository genelindeki blueprint ID benzersizliğini de denetler.

## 6. Tek kayıtla uçtan uca CLI testi

Depodaki `single_tool.json` test fixture'ı, üretim kataloğu oluşturmadan güvenli
bir altyapı smoke testi sağlar. Bu fixture dataset içeriği olarak yayımlanmaz.

### 6.1 Provider ve sözleşme kontrolü

```powershell
.\.venv\Scripts\magibu-toolcall.exe provider check --provider all --confirm-live --output json
.\.venv\Scripts\magibu-toolcall.exe blueprint validate tests\fixtures\blueprints\valid\single_tool.json --registry registry\registry.jsonl
```

İlk komut canlıdır; ikinci komut tamamen yereldir.

### 6.2 Aday üretimi

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset generate tests\fixtures\blueprints\valid\single_tool.json `
  --registry registry\registry.jsonl `
  --job-id dataset-smoke-001 `
  --output data\dataset\staging\dataset-smoke-001.jsonl `
  --start-number 1 `
  --max-workers 1 `
  --token-budget 20000 `
  --execute-live
```

Komut blueprint ve registry checksum’larını sabitler; manifest, checkpoint ve
çalışma kanıtlarını `runs/dataset/dataset-smoke-001/` altında tutar. Üretilen
kayıt otomatik olarak insan onaylı sayılmaz. Aynı tamamlanmış job yerinde yeniden
çalıştırılmaz; yeni denemede benzersiz bir `--job-id` ve output yolu kullanın.

### 6.3 Üretim sonrası doğrulama sınırı

`dataset generate`, yazmadan önce blueprint'i ve üretilen kaydı komutta verilen
registry ile doğrular. Bağımsız `dataset validate` komutu varsayılan canonical
registry'yi kullanır ve `--registry` seçeneği sunmaz. Bu smoke testi canonical
demo registry kullandığı için üretilen kayıt bağımsız olarak da doğrulanabilir.
Gelecekte proposal tool'larıyla üretilen kayıtlar aynı registry yolu verilerek
`dataset quality` içinde yeniden doğrulanır.

Smoke çıktısı ve hazır test kaydı şu şekilde doğrulanabilir:

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset validate tests\fixtures\dataset\valid_single_tool.json --output json
.\.venv\Scripts\magibu-toolcall.exe dataset validate data\dataset\staging\dataset-smoke-001.jsonl --output json
```

### 6.4 Execution, duplicate ve OpenAI kalite kontrolü

Accepted referans dosyası henüz yoksa `--reference` vermeyin:

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset quality `
  data\dataset\staging\dataset-smoke-001.jsonl `
  data\dataset\needs_revision\dataset-smoke-001.pr.review.jsonl `
  --registry registry\registry.jsonl `
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
`metadata.review.status` değerini `accepted` yapmaz ve insan dili kapısını bilinçli
olarak `not_run` bırakır. `.pr.review.jsonl` adayını ve eşleşen
`.pr.quality.json` raporunu GitHub PR'a ekleyin. Reviewer doğal Türkçe ile teknik
kanıtları onayladıktan sonra language/review yaşam döngüsü alanları aynı PR'da
güncellenir ve son CI yeniden çalıştırılır. Kabul, ancak korumalı PR'ın güncel
hâli onaylanıp merge edildiğinde repository açısından geçerli olur.

## 7. Toplu üretim

Normal başlangıç komutu `dataset generate`’dır. Ayrı `batch plan/run` komutları
yalnız önceden planlanmış işi devam ettirmek veya özel shard yönetmek içindir.

```powershell
$BlueprintFile = "blueprints\<domain>_<source>.jsonl"
$ProposalRegistry = "registry\proposals"
$JobId = "dataset-batch-001"
.\.venv\Scripts\magibu-toolcall.exe dataset generate $BlueprintFile `
  --registry $ProposalRegistry `
  --job-id $JobId `
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
$Manifest = "runs\dataset\$JobId\manifest.json"
.\.venv\Scripts\magibu-toolcall.exe dataset batch status $Manifest --output json
.\.venv\Scripts\magibu-toolcall.exe dataset batch report $Manifest --output json
```

1.000 kayıt tek kontrolsüz çağrı olarak üretilmemelidir. Önerilen hazırlık
kapıları 30, 100 ve 250 kayıttır; bunlar ölçek kararını doğrulayan pilotlardır ve
nihai release sayımına otomatik olarak eklenmez. Her kapıda hata türleri,
tool/kategori/kaynak dağılımı, duplicate oranı, insan inceleme uyumu, token
kullanımı ve provider maliyeti değerlendirilir. Onaydan sonra 1.000 kayıtlık hedef
dört ayrı 250 kayıtlık üretim işiyle oluşturulabilir.

## 8. GitHub katkı kontrolü

Katkı botu PR açıklamasını ve dosya paketini yorumlar; teknik `validate` kontrolü
testleri çalıştırır; nihai kararı insan reviewer verir. Workflow güvenlik sınırı,
ilk kurulum davranışı ve önerilen branch kuralları
[review alanı belgesinde](review/README.md) tutulur. Katkı paketinin zorunlu
içeriği için [CONTRIBUTING.md](CONTRIBUTING.md) kullanılmalıdır.

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

PR incelemesinde `accepted` yaşam döngüsü alanları verilmiş girişten canonical
accepted dosyasını üretme:

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset export data\dataset\needs_revision\dataset-release-v1.pr.review.jsonl data\dataset\accepted\dataset.jsonl
```

CLI GitHub approval durumunu API üzerinden sorgulamaz. Girişteki `accepted`
alanlarının korumalı PR süreciyle verildiği repository yönetimi tarafından
garanti edilmelidir; export komutu kayıtları yeniden doğrular ve diğer yaşam
döngüsü durumlarını dışarıda bırakır.

Eğitim sistemine verilecek metadata’sız görünüm:

```powershell
.\.venv\Scripts\magibu-toolcall.exe dataset export data\dataset\accepted\dataset.jsonl .cache\exports\dataset-training.jsonl --projection training
```

Training projection yalnız `id`, `messages` ve `tools` alanlarını içerir.
Canonical dosya provenance, execution ve kalite kanıtlarını korur. `.cache`
altındaki projection yerel çalışma çıktısıdır ve Git tarafından yok sayılır.

## 11. Askıdaki alanlar

xLAM/When2Call import-lokalizasyon komutları kodda bulunur ancak aktif dataset
üretim prosedürüne dahil değildir. Benchmark doğrulama, kontaminasyon, freeze,
run ve report araçları da ayrı namespace altında mevcuttur; benchmark aday
üretimi ise çalışma zamanında açıkça engellenir. Bu alanlar yeniden açıldığında
kaynak kullanım koşulları, ayrı review planı ve benchmark
kontaminasyon/freeze kapıları onaylanmadan üretim yapılmamalıdır.

Benchmark yaşam döngüsü için [ayrı belgeye](data/benchmark/README.md) bakın.

## 12. Dizinler ve Git politikası

```text
blueprints/<domain>_<source>.jsonl  İzlenen blueprint katkısı ve regresyonlar
registry/                           Canonical registry ve fixture’lar
registry/proposals/<domain>_<source>.jsonl  Candidate tool parçası
registry/proposals/fixtures/        Proposal fixture’ları
src/tool_call_tr/execution/local/   Yerel executor modülleri
src/tool_call_tr/execution/simulation/  Simülasyon tool modülleri
data/snapshots/                     Sürümlenmiş kaynak snapshot’ları (izlenir)
scripts/snapshots/                  Snapshot dönüştürme scriptleri
data/dataset/staging/               Yerel üretilmiş adaylar
data/dataset/needs_revision/        PR’a seçilerek eklenen review adayları
data/dataset/accepted/dataset.jsonl Canonical accepted dataset
review/dataset/                     PR’a seçilerek eklenen kalite raporları
runs/dataset/                       Yerel manifest/checkpoint/provider kanıtları
schemas/                            JSON Schema sözleşmeleri
```

`.gitignore` dataset/benchmark ham girdilerini, staging, run ve genel üretilmiş
çıktıları dışarıda bırakır. Yalnız `<job_id>.pr.review.jsonl`,
`<job_id>.pr.quality.json` ve canonical `accepted/dataset.jsonl` açıkça review
edilebilir yollar olarak izlenebilir. `data/snapshots/` bu kuralın dışındadır:
snapshot'ın ham kaynak dosyaları denetim kanıtı olduğu için bilerek commit
edilir; sözleşme
[execution ortamları belgesindedir](docs/execution_environments.md).

## 13. Son doğrulama

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\magibu-toolcall.exe registry validate registry\registry.jsonl
git status --short
```

Testlerin geçmesi, canlı kaynakların lisans veya veri kalitesi onayı anlamına
gelmez; bu kararlar PR kanıtı ve insan incelemesi gerektirir.
