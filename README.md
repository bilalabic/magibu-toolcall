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

## Güncel çalışma odağı

Aktif geliştirme odağı doğrudan Türkçe genel senaryolar (`original_turkish`) ve
Türkiye-native senaryolardır (`turkey_native`). xLAM/When2Call çeviri-lokalizasyon
hattı ile benchmark yaşam döngüsü şimdilik askıdadır. Bu altyapılar silinmez;
üretim, veri indirme, lokalizasyon veya benchmark çalıştırması yapılmaz.

Aktif dataset hattında sade komut kullanımı kalite kapılarını kaldırmaz. Manifest,
input checksum, checkpoint, provenance, registry/şema kontrolü, ID çakışma
kontrolü, hata kuyruğu ve audit kaydı otomatik olarak korunur. Model çıktısı kendi
başına kalite onayı sayılmaz.

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
runs/dataset/...   -> üretim manifest, checkpoint ve hata kayıtları
runs/...           -> diğer kontrollü çalışma ve değerlendirme sonuçları
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

Dataset kalite operatörü `quality_check`, reviewer’lar ise rollerine göre
`review` ve `accept` izinlerine sahip olmalıdır. Gerçek API’nin kalite kontrolü
aynı actor için ayrıca `platform/real_api` yetkisi gerektirir.

```text
magibu-toolcall access validate configs/access-policy.json
magibu-toolcall access check configs/access-policy.json --actor-id rev_language_01 --lifecycle dataset --permission accept --reviewer-role language
magibu-toolcall access verify-audit review/dataset/audit.jsonl --output json
```

`benchmark_dataset_team_exclusive=true` olduğunda aynı principal hem dataset hem
benchmark ekibinde yer alamaz. CLI politikası dosya sistemi güvenliği yerine
geçmez; benchmark klasörlerine ayrıca işletim sistemi veya nesne depolama ACL’i
uygulanmalıdır.

## 1. xLAM ve When2Call içe aktarma — askıda

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

## 2. Türkçe lokalizasyon — askıda

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

## 3. Türkçe senaryo üretimi

Normal akışta blueprint dosyası doğrudan `dataset generate` komutuna verilir.
CLI bütün blueprint’leri canlı model çağrısından önce doğrular; tek job içinde
yalnızca bir kaynak türüne izin verir. Manifest, input checksum, shard,
checkpoint, hata kuyruğu, hedef dağılım ve ID planı otomatik oluşturulur.

```text
magibu-toolcall dataset generate blueprints/pilot.jsonl --job-id dataset-pilot-001 --execute-live --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl
```

`--output` verilmezse adaylar
`data/dataset/staging/<job_id>.jsonl` yoluna yazılır. İş kanıtları
`runs/dataset/<job_id>/` altında tutulur. `--start-number` verilmezse ilgili
kaynak türünün mevcut dataset kayıtları taranarak sıradaki çakışmasız numara
seçilir. Blueprint’lerdeki `source_type` yalnız `original_turkish` veya
`turkey_native` olabilir.

Modelin döndürdüğü `accepted`, reviewer veya validation beyanları güvenilir kabul
edilmez. CLI bunları kanıta dayalı draft durumuna çevirir:

- Blueprint metadata’sı, exposed tool listesi, beklenen tool call ve tool result değiştirilemez.
- Provider/model kimliği ve blueprint bağlantısı provenance’a sistem tarafından yazılır.
- Kayıt daima `needs_revision` ve reviewersız başlar.
- Çalıştırılmayan execution, semantik, dil ve tekrar kontrolleri `not_run` kalır.
- `not_run` veya `failed` bir kalite aşaması varken kayıt `accepted` olamaz.

Üretimden sonra otomatik kalite kanıtları ayrı komutla hesaplanır:

```text
magibu-toolcall dataset quality data/dataset/staging/dataset-pilot-001.jsonl data/dataset/needs_revision/dataset-pilot-001.jsonl --reference data/dataset/accepted/dataset.jsonl --semantic-provider openai --semantic-threshold 0.90 --report review/dataset/dataset-pilot-001.quality.json --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl
```

Bu komut şema ve tool-call yapısını yeniden doğrular; local/mock çağrıları
gerçekten çalıştırıp kayıt içindeki tool result ile karşılaştırır. Exact ve
normalize tekrar kontrolü her zaman yapılır. `openai` seçildiğinde üretim
embedding modeliyle semantik karşılaştırma yapılır. `token-test-double` yalnız
test içindir ve semantik kapısını `passed` yapamaz. Karşılaştırılacak başka kayıt
yoksa semantik kapısı `not_applicable` olur. `--reference` dosyaları yalnızca
önceden kabul edilmiş dataset kayıtları içerebilir; aynı ID’nin yeniden
kullanılması engellenir.

`real_api` execution yalnız `--confirm-live` ve gerekli platform izniyle
çalıştırılır. Yetki veya adaptör bulunmayan execution türü sessizce geçilmiş
sayılmaz; `not_run` kalır. Ayrıntılı execution ve duplicate kanıtları kalite
raporuna yazılır. Otomatik kalite komutu insan onayı vermez.

Hedef dağılım dosyası örneği:

```json
{
  "main_category": {"single_tool": 40, "no_tool": 15, "missing_parameter": 15, "multi_turn": 20, "multi_tool": 10},
  "source_type": {"original_turkish": 70, "turkey_native": 30}
}
```

`--targets` verilmezse `main_category`, `source_type`, `domain` ve `difficulty`
dağılımları blueprint girdisinden otomatik dondurulur. Özel hedef dosyası
verilirse toplamlar ve metadata dağılımı blueprint girdisiyle birebir eşleşmek
zorundadır.

```text
magibu-toolcall dataset batch status runs/dataset/dataset-pilot-001/manifest.json --output json
magibu-toolcall dataset batch run runs/dataset/dataset-pilot-001/manifest.json --execute-live --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl
magibu-toolcall dataset batch report runs/dataset/dataset-pilot-001/manifest.json --output json
```

`dataset batch run` yalnız önceden planlanmış veya kesilmiş işi devam ettirmek
için ileri seviye komuttur. Tamamlanan iş immutable kabul edilir; yeniden
çalıştırmak için yeni `job_id` gerekir.

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
magibu-toolcall dataset quality data/dataset/staging/candidates.jsonl data/dataset/needs_revision/candidates.jsonl --reference data/dataset/accepted/dataset.jsonl --semantic-provider openai --semantic-threshold 0.90 --semantic-cache .cache/semantic --actor-id dataset_operator_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall benchmark contamination-check --benchmark data/benchmark/staging/candidates.jsonl --dataset data/dataset/accepted/dataset.jsonl --semantic-provider openai --semantic-threshold 0.90 --semantic-cache .cache/semantic --output json
```

Embedding’ler provider model kimliğine ve metin SHA-256 değerine göre önbelleğe
alınır. Model veya eşik seçimi raporda sabitlenmeli ve ekip tarafından
onaylanmalıdır.

## 6. İnceleme ve export

```text
magibu-toolcall dataset review data/dataset/needs_revision/candidates.jsonl review/dataset/language-reviewed.jsonl --record-id tctr_ot_000001 --reviewer-id rev_language_01 --role language --decision approve --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset review review/dataset/language-reviewed.jsonl review/dataset/fully-reviewed.jsonl --record-id tctr_ot_000001 --reviewer-id rev_technical_01 --role technical --decision approve --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl

magibu-toolcall dataset export review/dataset/fully-reviewed.jsonl data/dataset/accepted/dataset.jsonl --actor-id dataset_lead_01 --policy configs/access-policy.json --audit-log review/dataset/audit.jsonl
```

`--decision approve`, reviewer’ın kendi perspektifindeki onayını kaydeder; genel
kayıt durumunu doğrudan zorlamaz. Dil onayı `validation.language` kapısını
tamamlar. Multi-tool, sequential ve açıkça işaretlenmiş kayıtlar iki farklı
reviewer ile hem dil hem teknik perspektifi gerektirir. Diğer kalite kapıları
eksikse reviewer onayı kaydedilir fakat kayıt `needs_revision` kalır. Contributor
kendi kaydını onaylayamaz.

Benchmark freeze/run komutları altyapıda korunur ancak güncel çalışma odağında
değildir ve bu aşamada kullanılmaz.

## Dizinler

- `schemas/`: Dataset, benchmark, registry, blueprint, source work item, batch job ve access-policy sözleşmeleri
- `registry/`: Kanonik tool kayıtları ve deterministik fixture’lar
- `blueprints/`: Dataset ve benchmark için ayrı üretim blueprint’leri
- `data/dataset/`: `raw`, `staging`, `needs_revision`, `rejected`, `accepted`
- `data/benchmark/`: Ayrı lifecycle ve ek olarak immutable `gold`
- `review/dataset/`, `review/benchmark/`: Ayrı review çıktıları ve audit logları
- `runs/dataset/`: Dataset job manifest, checkpoint, part ve hata kayıtları
- `runs/`: Diğer kontrollü çalışma ve değerlendirme kayıtları
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
