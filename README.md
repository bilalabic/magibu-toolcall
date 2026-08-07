# magibu-toolcall

`magibu-toolcall`, Türkçe araç çağırma dataset’i ile ondan fiziksel ve
operasyonel olarak bağımsız benchmark’ı üretmek, doğrulamak, incelemek ve
dondurmak için geliştirilmiş Python altyapısıdır.

Proje artık şu üretim temellerini içerir:

- Gerçek xLAM ve When2Call JSON/JSONL biçimlerini okuyan kaynak adaptörleri
- Makine alanlarını değiştirmeyen Türkçe lokalizasyon iş akışı
- DeepSeek üzerinden yapılandırılmış ve devam ettirilebilir toplu aday üretimi
- Türkiye-native araçlar için yalnız HTTPS `GET` kullanan gerçek JSON API adaptörü
- OpenAI embedding, cosine similarity, batching ve model-kimlikli disk önbelleği
- Aktif reviewer/operator dizini, lifecycle kapsamı, izin kontrolü ve hash-zincirli audit kaydı
- Checksum, shard, checkpoint, hata kuyruğu, ID çakışma ve dağılım kapıları
- Dataset’ten bağımsız benchmark üretimi, kontaminasyon kontrolü, freeze ve run kayıtları

Bu depo hâlâ tamamlanmış dataset veya benchmark değildir. Gerçek kaynak
dosyaları, reviewer kimlikleri, API/model kimlik bilgileri ve üretim çıktıları
depoya eklenmez. `schema_version` ve `tool_registry_version` şimdilik `0.1.0`’dır.

## Temel ayrım

Üç dataset kaynağı aynı kanonik dataset hattında yönetilir:

```text
translated          xLAM / When2Call gibi kaynaklardan lokalize edilen kayıtlar
original_turkish    doğrudan Türkçe üretilen genel araç senaryoları
turkey_native       Türkiye’deki kurum, açık veri veya yerel hizmet araçları
```

Benchmark bu üç kaynak türünü kullanabilir; ancak dataset’ten türetilmez,
dataset’e kopyalanmaz ve ayrı ekip/kapsam ile üretilir:

```text
data/dataset/...   -> tctr_tr_*, tctr_ot_*, tctr_tn_*
data/benchmark/... -> bench_tr_*, bench_ot_*, bench_tn_*
runs/...           -> yalnız model tahminleri ve değerlendirme sonuçları
```

## Kurulum

Python 3.11 veya daha yeni bir sürüm gereklidir.

```text
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

Windows üzerinde bütün doğrulamaları tek komutla çalıştırmak için:

```text
powershell -File scripts/verify.ps1
```

Dağıtım ve CLI adı `magibu-toolcall`, teknik Python import paketi
`tool_call_tr`’dir.

## Erişim politikası

Veri değiştiren üretim komutları bir access-policy dosyası ve audit yolu ister.
Politika biçimi [access_policy.schema.json](schemas/access_policy.schema.json)
tarafından tanımlanır. Gerçek ekip kimlikleri bu depoda örnek olarak
uydurulmaz; dataset ve benchmark sorumluları tarafından atanır.

```text
magibu-toolcall access validate configs/access-policy.json
magibu-toolcall access check configs/access-policy.json --actor-id rev_language_01 --lifecycle dataset --permission accept --reviewer-role language
magibu-toolcall access verify-audit review/dataset/audit.jsonl --output json
```

`benchmark_dataset_team_exclusive=true` olduğunda aynı principal hem dataset hem
benchmark ekibinde yer alamaz. CLI politikası dosya sistemi güvenliği yerine
geçmez; benchmark klasörlerine ayrıca işletim sistemi veya nesne depolama ACL’i
uygulanmalıdır.

## 1. xLAM ve When2Call içe aktarma

xLAM dosyaları Hugging Face üzerinde koşul kabulü gerektirir. CLI bu koşulları
kullanıcı adına kabul etmez ve kaynağı otomatik indirmez. Operatör, erişim
koşullarını kendisi kabul edip yerel JSON/JSONL dosyasını sağladıktan sonra açıkça
`--source-terms-accepted` verir. When2Call test, SFT ve preference biçimleri alan
yapılarına göre ayrıştırılır; güvenilir karar etiketi bulunmayan eğitim satırları
`needs_source_review` olarak kalır.

Küçük bir yerel dosyayı doğrudan içe aktarma:

```text
magibu-toolcall dataset source import upstream/xlam.jsonl data/dataset/raw/xlam-import.jsonl --source xlam --split train --source-terms-accepted --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset source import upstream/when2call.jsonl data/dataset/raw/when2call-import.jsonl --source when2call --split test --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset source validate data/dataset/raw/xlam-import.jsonl
```

Büyük dosyada checksum, shard ve resume kullanmak için önce iş planlanır:

```text
magibu-toolcall dataset batch plan upstream/xlam.jsonl data/dataset/staging/jobs/xlam-import/job.json --job-id xlam-import-001 --operation source_import --output data/dataset/raw/xlam-import.jsonl --checkpoint data/dataset/staging/jobs/xlam-import/checkpoint.json --errors data/dataset/staging/jobs/xlam-import/errors.jsonl --shard-size 250 --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset source import-job data/dataset/staging/jobs/xlam-import/job.json --source xlam --split train --source-terms-accepted --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset batch status data/dataset/staging/jobs/xlam-import/job.json --output json
```

İçe aktarılan iş kaydı kanonik dataset değildir. Kaynak dataset/split/örnek ID,
lisans zinciri, ham satır SHA-256 özeti, normalize araçlar ve lokalizasyon durumu
taşır. Bu kayıt yanlışlıkla `accepted` alanına aktarılamaz.

## 2. Türkçe lokalizasyon

Manuel veya haricî olarak hazırlanmış patch dosyası; `source_example_id`, Türkçe
`query`, araç açıklamaları, parametre açıklamaları, gerekiyorsa Türkçe `response`,
`actor_id`, `provider` ve `provider_version` alanlarını taşır. Function adları,
parametre anahtarları, enum değerleri, tool-call argümanları ve karar etiketi
değiştirilemez.

```text
magibu-toolcall dataset source localize data/dataset/raw/xlam-import.jsonl localization/patches.jsonl data/dataset/staging/xlam-localized.jsonl --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl
```

DeepSeek ile toplu lokalizasyon için `source_localization` işi planlanır ve açık
canlı çağrı onayı verilir:

```text
magibu-toolcall dataset batch plan data/dataset/raw/xlam-import.jsonl data/dataset/staging/jobs/xlam-localize/job.json --job-id xlam-localize-001 --operation source_localization --output data/dataset/staging/xlam-localized.jsonl --checkpoint data/dataset/staging/jobs/xlam-localize/checkpoint.json --errors data/dataset/staging/jobs/xlam-localize/errors.jsonl --shard-size 100 --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset source generate-localizations data/dataset/staging/jobs/xlam-localize/job.json --provider deepseek --execute-live --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl
```

Üretilen lokalizasyonlar `localized_needs_review` veya
`localized_needs_source_review` durumunda kalır; insan onayı otomatik verilmez.

## 3. Toplu Türkçe senaryo üretimi

Dataset ve benchmark üretimi ayrı manifestlerle yapılır. Her input blueprint bir
aday üretir. Manifest; input checksum’ını, shard sınırlarını, output/error yollarını,
hedef dağılımı ve ayrılmış ID aralığını sabitler. `--existing` ile verilen mevcut
dosyalardaki ID’lerle çakışma plan aşamasında engellenir.

Hedef dağılım dosyası örneği:

```json
{
  "main_category": {"single_tool": 40, "no_tool": 15, "missing_parameter": 15, "multi_turn": 20, "multi_tool": 10},
  "source_type": {"translated": 35, "original_turkish": 35, "turkey_native": 30}
}
```

Bu toplamlar input blueprint sayısıyla ve blueprint metadata dağılımıyla birebir
eşleşmek zorundadır.

```text
magibu-toolcall dataset batch plan blueprints/dataset.jsonl data/dataset/staging/jobs/pilot/job.json --job-id dataset-pilot-001 --operation scenario_generation --output data/dataset/staging/candidates.jsonl --checkpoint data/dataset/staging/jobs/pilot/checkpoint.json --errors data/dataset/staging/jobs/pilot/errors.jsonl --shard-size 25 --targets configs/dataset-targets.json --source-type original_turkish --start-number 1 --existing data/dataset/accepted/dataset.jsonl --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset generate data/dataset/staging/jobs/pilot/job.json --provider deepseek --execute-live --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset batch report data/dataset/staging/jobs/pilot/job.json --output json
```

Benchmark için `benchmark_generation`, `bench_*` ID aralığı, benchmark kapsamlı
principal ve ayrı output yolları kullanılır:

```text
magibu-toolcall benchmark batch plan blueprints/benchmark.jsonl data/benchmark/staging/jobs/pilot/job.json --job-id benchmark-pilot-001 --operation benchmark_generation --output data/benchmark/staging/candidates.jsonl --checkpoint data/benchmark/staging/jobs/pilot/checkpoint.json --errors data/benchmark/staging/jobs/pilot/errors.jsonl --shard-size 25 --source-type original_turkish --start-number 1 --actor-id benchmark_lead_01 --policy configs/access-policy.json --audit-log review/benchmark/audit.jsonl

magibu-toolcall benchmark generate data/benchmark/staging/jobs/pilot/job.json --provider deepseek --execute-live --actor-id benchmark_lead_01 --policy configs/access-policy.json --audit-log review/benchmark/audit.jsonl
```

Yarıda kalan iş aynı manifestle devam eder. Tamamlanan iş immutable kabul edilir;
yeniden çalıştırmak için yeni `job_id` ve yeni yollar gerekir.

## 4. Türkiye-native gerçek API araçları

Gerçek API sözleşmesi Tool Registry kaydındaki `execution.http` alanında tutulur.
Adaptör yalnız şu sözleşmeleri çalıştırır:

- `https://` URL
- Yalnız `GET`
- Açık host allowlist’i
- Bütün function parametrelerini kapsayan query map
- Ortam değişkeninden okunan kimlik bilgisi
- Sabit timeout ve JSON response path
- `side_effects=false`

Nihai Türkiye API/tool listesi bu altyapı tarafından seçilmez. Kaynak, lisans,
erişim koşulları ve fixture planı araştırıldıktan sonra registry kaydı `approved`
olmalıdır. Canlı çağrı ayrıca açıkça onaylanır:

```text
magibu-toolcall registry validate registry/registry.jsonl
magibu-toolcall tool run-api kurum_veri_ara --arguments "{\"query\":\"örnek\"}" --confirm-live --actor-id platform_operator_01 --policy configs/access-policy.json --audit-log review/platform-audit.jsonl
```

HTTP response gövdesi veya credential hata mesajına eklenmez. Sonuçlar
`passed`, `failed`, `timeout`, `rate_limited`, `empty_result` veya
`invalid_result` olarak normalize edilir.

## 5. Üretim semantik benzerlik

`token-test-double` yalnız yerel ve deterministik test içindir. Üretimde OpenAI
embedding modeli açıkça yapılandırılır:

```text
MAGIBU_TOOLCALL_OPENAI_API_KEY
MAGIBU_TOOLCALL_OPENAI_EMBEDDING_MODEL
MAGIBU_TOOLCALL_OPENAI_BASE_URL
MAGIBU_TOOLCALL_SEMANTIC_CACHE_DIR
```

```text
magibu-toolcall dataset check-duplicates data/dataset/staging/candidates.jsonl --semantic-provider openai --semantic-threshold 0.90 --semantic-cache .cache/semantic --output json

magibu-toolcall benchmark contamination-check --benchmark data/benchmark/staging/candidates.jsonl --dataset data/dataset/accepted/dataset.jsonl --semantic-provider openai --semantic-threshold 0.90 --semantic-cache .cache/semantic --output json
```

Embedding’ler provider model kimliğine ve metin SHA-256 değerine göre önbelleğe
alınır. Model veya eşik seçimi raporda sabitlenmeli ve ekip tarafından
onaylanmalıdır.

## 6. İnceleme, export ve benchmark freeze

```text
magibu-toolcall dataset review data/dataset/staging/candidates.jsonl review/dataset/reviewed.jsonl --record-id tctr_ot_000001 --reviewer-id rev_language_01 --role language --status accepted --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset export review/dataset/reviewed.jsonl data/dataset/accepted/dataset.jsonl --actor-id dataset_lead_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl
```

Contributor kendi kaydına final onayı veremez. Multi-tool, sequential ve açıkça
işaretlenmiş kayıtlar iki farklı reviewer ile hem dil hem teknik perspektifi
gerektirir.

Benchmark ancak kabul edilmiş dataset snapshot’ına karşı kontaminasyon kapısını
geçerse dondurulur:

```text
magibu-toolcall benchmark freeze data/benchmark/accepted/benchmark.jsonl data/benchmark/gold/gold.jsonl --dataset data/dataset/accepted/dataset.jsonl --freeze-id pilot-001 --semantic-provider openai --actor-id benchmark_lead_01 --policy configs/access-policy.json --audit-log review/benchmark/audit.jsonl

magibu-toolcall benchmark verify-freeze data/benchmark/gold/gold.jsonl data/benchmark/gold/gold.jsonl.manifest.json

magibu-toolcall benchmark run data/benchmark/gold/gold.jsonl predictions.jsonl --model-name model-name --run-id run-001 --actor-id benchmark_lead_01 --policy configs/access-policy.json --audit-log review/benchmark/audit.jsonl
```

Gold kayıtlar değiştirilmez; tahminler `runs/<model_name>/<run_id>.jsonl`
altında tutulur.

## Dizinler

- `schemas/`: Dataset, benchmark, registry, blueprint, source work item, batch job ve access-policy sözleşmeleri
- `registry/`: Kanonik tool kayıtları ve deterministik fixture’lar
- `blueprints/`: Dataset ve benchmark için ayrı üretim blueprint’leri
- `data/dataset/`: `raw`, `staging`, `needs_revision`, `rejected`, `accepted`
- `data/benchmark/`: Ayrı lifecycle ve ek olarak immutable `gold`
- `review/dataset/`, `review/benchmark/`: Ayrı review çıktıları ve audit logları
- `runs/`: Yalnız benchmark model çalıştırma kayıtları
- `src/tool_call_tr/`: CLI ve bütün uygulama modülleri
- `tests/`: Canlı credential veya ağ gerektirmeyen deterministik testler

## Ortam değişkenleri

Desteklenen önek yalnız `MAGIBU_TOOLCALL_*`’dır. Eski `TOOL_CALL_TR_*` öneki
okunmaz.

```text
MAGIBU_TOOLCALL_DEEPSEEK_API_KEY
MAGIBU_TOOLCALL_DEEPSEEK_MODEL
MAGIBU_TOOLCALL_DEEPSEEK_BASE_URL
MAGIBU_TOOLCALL_OPENAI_API_KEY
MAGIBU_TOOLCALL_OPENAI_MODEL
MAGIBU_TOOLCALL_OPENAI_EMBEDDING_MODEL
MAGIBU_TOOLCALL_OPENAI_BASE_URL
MAGIBU_TOOLCALL_REQUEST_TIMEOUT_SECONDS
MAGIBU_TOOLCALL_MAX_RETRIES
MAGIBU_TOOLCALL_RETRY_BASE_SECONDS
MAGIBU_TOOLCALL_SEMANTIC_CACHE_DIR
MAGIBU_TOOLCALL_LOG_LEVEL
MAGIBU_TOOLCALL_ROOT
```

Gerçek secret değerleri `.env.example`, registry, manifest, audit, hata kuyruğu
veya test fixture’larına yazılmamalıdır.

## Doğrulama

```text
.venv/Scripts/python -m pytest
powershell -File scripts/verify.ps1
```

Testler canlı API çağrısı yapmaz. HTTP ve provider testleri enjekte edilmiş
taşıyıcılarla request/response, timeout, rate-limit, invalid JSON, secret
redaction, cache ve retry davranışlarını doğrular. Canlı üretim ancak ilgili
credential, onaylı politika ve açık `--execute-live`/`--confirm-live` seçeneğiyle
başlatılır.

Sonraki güvenli adım, gerçek ekip principal’larını atamak; küçük bir onaylı tool
grubunu belirlemek; xLAM/When2Call kaynak koşullarını kayıt altına almak ve
20–30 blueprint’lik teknik pilotu yeni batch manifestleriyle çalıştırmaktır.
