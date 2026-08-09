# magibu-toolcall — teknik kullanım rehberi

[← Proje tanıtımına, yeteneklere ve sınırlara dön](README.md)

`magibu-toolcall`, Türkçe araç çağırma dataset’i ile ondan fiziksel ve
operasyonel olarak bağımsız benchmark’ı üretmek, doğrulamak, incelemek ve
dondurmak için geliştirilmiş Python altyapısıdır.

Proje artık şu üretim temellerini içerir:

- Gerçek xLAM ve When2Call JSON/JSONL biçimlerini okuyan kaynak adaptörleri
- Makine alanlarını değiştirmeyen Türkçe lokalizasyon iş akışı
- DeepSeek üzerinden token bütçeli, sınırlı paralel ve devam ettirilebilir toplu aday üretimi
- Türkiye-native araçlar için yalnız HTTPS `GET` kullanan gerçek JSON API adaptörü
- OpenAI embedding/cosine tekrar taraması ve primary/escalation kalite judge akışı
- GitHub pull request incelemesi, branch protection ve otomatik durum kontrolü
- Checksum, shard, checkpoint, hata kuyruğu, ID çakışma ve dağılım kapıları
- Dataset’ten bağımsız benchmark üretimi, kontaminasyon kontrolü, freeze ve run kayıtları

Bu depo hâlâ tamamlanmış dataset veya benchmark değildir. Gerçek kaynak
dosyaları, API/model kimlik bilgileri ve üretim çıktıları depoya eklenmez.
Reviewer kimliği ve karar geçmişi GitHub PR üzerinde tutulur. `schema_version`
ve `tool_registry_version` şimdilik `0.1.0`’dır.

## İçindekiler

- [Güncel çalışma odağı](#güncel-çalışma-odağı)
- [Temel dataset ve benchmark ayrımı](#temel-ayrım)
- [Kurulum ve API anahtarları](#kurulum)
- [GitHub PR incelemesi](#github-pr-incelemesi)
- [Askıdaki kaynak içe aktarma ve lokalizasyon](#1-xlam-ve-when2call-içe-aktarma--askıda)
- [Aday tool sözleşmelerini sınama](#aday-tool-sözleşmelerini-cli-ile-sınama)
- [Türkçe senaryo üretimi](#3-türkçe-senaryo-üretimi)
- [Türkiye-native gerçek API araçları](#4-türkiye-native-gerçek-api-araçları)
- [Semantik benzerlik, insan incelemesi ve export](#5-üretim-semantik-benzerlik)
- [Dizinler, ortam değişkenleri ve doğrulama](#dizinler)

## Güncel çalışma odağı

Aktif geliştirme odağı doğrudan Türkçe genel senaryolar (`original_turkish`) ve
Türkiye-native senaryolardır (`turkey_native`). xLAM/When2Call çeviri-lokalizasyon
hattı ile benchmark yaşam döngüsü şimdilik askıdadır. Bu altyapılar silinmez;
üretim, veri indirme, lokalizasyon veya benchmark çalıştırması yapılmaz.

Aktif dataset hattında sade komut kullanımı kalite kapılarını kaldırmaz. Manifest,
input checksum, checkpoint, provenance, registry/şema kontrolü, ID çakışma
kontrolü, hata kuyruğu ve kalite raporu otomatik olarak korunur. Model çıktısı kendi
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

### API anahtarlarını yerel olarak tanımlama

Anahtarları sohbete, komut satırı argümanına veya Git ile izlenen bir dosyaya
yazmayın. Proje kökündeki `.env` dosyası `.gitignore` kapsamındadır ve CLI
tarafından otomatik okunur. İlk kurulum:

```powershell
Copy-Item .env.example .env
notepad .env
```

`.env` içinde en az şu değerleri doldurun; gerçek değerlerin çevresine `< >`
yazmayın:

```text
MAGIBU_TOOLCALL_DEEPSEEK_API_KEY=<DeepSeek anahtarınız>
MAGIBU_TOOLCALL_DEEPSEEK_MODEL=deepseek-v4-flash
MAGIBU_TOOLCALL_DEEPSEEK_FALLBACK_MODEL=deepseek-v4-pro
MAGIBU_TOOLCALL_OPENAI_API_KEY=<OpenAI proje anahtarınız>
MAGIBU_TOOLCALL_OPENAI_MODEL=gpt-5.4-mini-2026-03-17
MAGIBU_TOOLCALL_OPENAI_ESCALATION_MODEL=gpt-5.4-2026-03-05
MAGIBU_TOOLCALL_OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Anahtarların değerlerini göstermeden yapılandırmayı kontrol edin:

```powershell
.\.venv\Scripts\magibu-toolcall.exe config
```

Yapılandırılmış model kimliklerinin sağlayıcı hesaplarında gerçekten erişilebilir
olduğunu, içerik üretmeden doğrulayın:

```powershell
.\.venv\Scripts\magibu-toolcall.exe provider check --confirm-live --output json
```

Bu komut yalnızca DeepSeek ve OpenAI `GET /models` uçlarını çağırır. API
anahtarlarını veya sağlayıcı yanıt gövdelerini yazdırmaz; `--confirm-live`
verilmeden ağ isteği yapmayı reddeder.

Flash–Pro karşılaştırmasında önce aynı üretim yoluyla tek blueprint smoke testi
yapılır. DeepSeek yalnız doğal Türkçe mesaj alanlarını üretir; tool şemaları,
call ID'leri, argümanlar, sonuçlar ve metadata kod tarafından deterministik
kurulur. Han/Çince karakteri veya `<think>` sızıntısı otomatik olarak reddedilir.

```powershell
.\.venv\Scripts\magibu-toolcall.exe provider compare-generation `
  blueprints\pilot_general.jsonl blueprints\pilot_turkey_native.jsonl `
  --registry registry\proposals\pilot_candidates.jsonl `
  --output-dir runs\provider-comparison\flash-pro-smoke `
  --limit 1 --judge-provider openai --max-workers 1 --confirm-live
```

Smoke testi temizse `--limit 1` kaldırılarak aynı 30 blueprint iki modelle de
çalıştırılır. Çıktı dizininde iki aday JSONL dosyası ve OpenAI puanları, token
kullanımı, request kimlikleri ve karar kuralını içeren `report.json` oluşur.
30 eşleşmiş örnek ve Flash için 30/30 OpenAI `pass` tamamlanmadan rapor
`Flash-first` politikasını kabul etmez.
Var olan bir karşılaştırmayı bilerek yenilemek için ayrıca `--overwrite`
verilmelidir.

7 Ağustos 2026 tarihli düzeltilmiş pilot koşusunda Flash 30/30 üretim ve 30/30
OpenAI `pass` ile 4,9857 ortalama; Pro 30/30 üretim, 28/30 `pass` ve 4,9191
ortalama elde etti. Karar kuralı bu nedenle `Flash-first, Pro fallback`
politikasını kabul etti. Ham rapor request kimlikleri ve çalışma kanıtları
içerdiği için `runs/provider-comparison/flash-pro-30-v4/report.json` altında
yerel tutulur ve Git'e eklenmez.

Belirli kayıtların regresyonu için `--blueprint-id` tekrarlanabilir. Bu seçim
kaynak dosyalarındaki sırayı korur ve bilinmeyen bir kimlikte ağ isteği
başlatmadan hata verir:

```powershell
.\.venv\Scripts\magibu-toolcall.exe provider compare-generation `
  blueprints\pilot_general.jsonl blueprints\pilot_turkey_native.jsonl `
  --registry registry\proposals\pilot_candidates.jsonl `
  --output-dir runs\provider-comparison\secilen-kayitlar `
  --blueprint-id bp_general_route_007 `
  --blueprint-id bp_general_knowledge_008 `
  --judge-provider openai --confirm-live
```

### 30 kayıtlık dataset pilotu

Model karşılaştırmasından sonra 15 genel ve 15 Türkiye-native blueprint normal
dataset CLI hattıyla ayrı işler olarak üretildi. Her iki iş de 15/15 üretim,
15/15 local/mock execution ve sıfır provider fallback ile tamamlandı. OpenAI
embedding taramasında her gruptaki 105 kayıt çifti incelendi ve duplicate
bulunmadı.

Otomatik kalite sonucu genel grupta 15/15, Türkiye-native grupta 14/15 `pass`
oldu. Reddedilen `tctr_tn_000009` kaydında doğal olmayan bir ifade, ham ISO
zamanları ve araç sonucundaki konumların atlanması birlikte görüldü. İlk pilot
çıktısı çalışma kanıtı olduğu için değiştirilmedi. Bunun yerine
`blueprints/regressions/parcel_natural_v2.jsonl` oluşturuldu; aynı kayıt Flash
ile yeniden üretildi ve hem birincil mini hem tam OpenAI hakeminden `pass` aldı.

İlk pilotta iki başka yanıtta ham ISO zaman, bir yanıtta da Markdown işareti
bulundu. Bunlar mevcut kalite raporlarının geçmiş kanıtıdır. Sonraki üretimlerde
ham ISO zaman damgası ve Markdown içeren doğal dil planları sağlayıcı yeniden
denemesine gönderilir. İnsan dil ve teknik incelemeleri hâlâ beklemektedir;
otomatik `pass` kayıtları doğrudan `accepted` durumuna taşımaz.

Çıktıda iki anahtar da yalnızca `<configured>` görünmelidir. OpenAI tarafında
ücretsiz paylaşımlı trafik kullanılacaksa aynı API projesi için data sharing
etkinleştirilmeli, teklif durumunun `enrolled` olduğu görülmeli ve hesapta pozitif
bakiye bulunmalıdır. Dataset'e gerçek kişi verisi, erişim anahtarı veya başka bir
secret konulmamalıdır.

Dağıtım ve CLI adı `magibu-toolcall`, teknik Python import paketi
`tool_call_tr`’dir.

## GitHub PR incelemesi

CLI kullanıcı hesabı, reviewer girişi, rol veya access-policy dosyası istemez.
İnsan incelemesinin güvenilir kaynağı GitHub pull request geçmişidir. Üretim ve
kalite komutları aday kaydı hazırlar; reviewer Türkçe, tool seçimi, argümanlar,
grounding, provenance, lisans ve güvenliği PR üzerinde kontrol eder.

`main` branch'i için pull request, en az bir onay, güncel branch ve `validate`
durum kontrolü zorunlu yapılmalıdır. Yeni commit geldiğinde eski onayın düşürülmesi
önerilir. Yüksek riskli veya çok araçlı değişikliklerde PR üzerinden ikinci
reviewer istenir; uygulama içinde kalıcı reviewer rolleri oluşturulmaz.

Kayıttaki `review.status` yalnız yaşam döngüsü etiketidir. Reviewer kimliği ve
karar geçmişi GitHub'da tutulur. `accepted` kayıtların hiçbir validation kapısı
`failed` veya `not_run` olamaz; export bu kuralı doğrulamaya devam eder.

## 1. xLAM ve When2Call içe aktarma — askıda

xLAM dosyaları Hugging Face üzerinde koşul kabulü gerektirir. CLI bu koşulları
kullanıcı adına kabul etmez ve kaynağı otomatik indirmez. Operatör, erişim
koşullarını kendisi kabul edip yerel JSON/JSONL dosyasını sağladıktan sonra açıkça
`--source-terms-accepted` verir. When2Call test, SFT ve preference biçimleri alan
yapılarına göre ayrıştırılır; güvenilir karar etiketi bulunmayan eğitim satırları
`needs_source_review` olarak kalır.

Küçük bir yerel dosyayı doğrudan içe aktarma:

```text
magibu-toolcall dataset source import upstream/xlam.jsonl data/dataset/raw/xlam-import.jsonl --source xlam --split train --source-terms-accepted

magibu-toolcall dataset source import upstream/when2call.jsonl data/dataset/raw/when2call-import.jsonl --source when2call --split test

magibu-toolcall dataset source validate data/dataset/raw/xlam-import.jsonl
```

Büyük dosyada checksum, shard ve resume kullanmak için önce iş planlanır:

```text
magibu-toolcall dataset batch plan upstream/xlam.jsonl data/dataset/staging/jobs/xlam-import/job.json --job-id xlam-import-001 --operation source_import --output data/dataset/raw/xlam-import.jsonl --checkpoint data/dataset/staging/jobs/xlam-import/checkpoint.json --errors data/dataset/staging/jobs/xlam-import/errors.jsonl --shard-size 250

magibu-toolcall dataset source import-job data/dataset/staging/jobs/xlam-import/job.json --source xlam --split train --source-terms-accepted

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
magibu-toolcall dataset source localize data/dataset/raw/xlam-import.jsonl localization/patches.jsonl data/dataset/staging/xlam-localized.jsonl
```

DeepSeek ile toplu lokalizasyon için `source_localization` işi planlanır ve açık
canlı çağrı onayı verilir:

```text
magibu-toolcall dataset batch plan data/dataset/raw/xlam-import.jsonl data/dataset/staging/jobs/xlam-localize/job.json --job-id xlam-localize-001 --operation source_localization --output data/dataset/staging/xlam-localized.jsonl --checkpoint data/dataset/staging/jobs/xlam-localize/checkpoint.json --errors data/dataset/staging/jobs/xlam-localize/errors.jsonl --shard-size 100

magibu-toolcall dataset source generate-localizations data/dataset/staging/jobs/xlam-localize/job.json --provider deepseek --execute-live
```

Üretilen lokalizasyonlar `localized_needs_review` veya
`localized_needs_source_review` durumunda kalır; insan onayı otomatik verilmez.

## Aday tool sözleşmelerini CLI ile sınama

Pilot adayları kanonik registry'ye alınmadan önce ayrı proposal registry'sinde
tutulur. Fixture komutu `--registry` verilince bu dosyayı kullanır; `--mode`
verilmezse sözleşmedeki varsayılan yürütme türünü seçer. Böylece yerel hesaplama
gerçek kodla, takvim dış sisteme dokunmayan simülasyonla, veri snapshot'ı henüz
hazır olmayan araçlar ise mock ile sınanır.

```text
magibu-toolcall registry validate registry/proposals/pilot_candidates.jsonl

magibu-toolcall blueprint validate blueprints/pilot_general.jsonl --registry registry/proposals/pilot_candidates.jsonl

magibu-toolcall tool run-fixture calculator.evaluate.basic --registry registry/proposals/pilot_candidates.jsonl

magibu-toolcall tool run-fixture calendar.create_event.confirmed --registry registry/proposals/pilot_candidates.jsonl

magibu-toolcall tool run-fixture earthquake.events.historical --registry registry/proposals/pilot_candidates.jsonl
```

Yürütme türünü sözleşmeye aykırı seçmek hata üretir; CLI sessizce başka moda
geçmez. `local_executable` etiketi yalnız uygulaması ve testi bulunan araçlara
verilir. Mock'tan yerel yürütmeye geçiş, ilgili veri snapshot'ı, lisans kaydı,
checksum ve deterministik adaptör tamamlandıktan sonra ayrıca onaylanır.

### Mock, simülasyon ve gerçek kaynak geçişi

30 kayıtlık teknik pilot bilinçli olarak güvenli yürütme ağırlıklıdır. Proposal
registry'deki 20 aracın 14'ü `mock`, 4'ü `local_executable`, 2'si
`fully_simulated` durumundadır. Pilot içindeki toplam 30 tool çağrısının 22'si
mock fixture üzerinden çalışmıştır. Bu dağılım altyapı pilotu için uygundur;
1000 kayıtlık üretim için tamamen sentetik fixture çeşitliliği yeterli değildir.

Gerçek API bulunduğunda mevcut mock ve simülasyonlar silinmez. Tool adı, giriş
şeması ve normalize çıkış şeması sabit tutularak ayrı `real_api` adaptörü
eklenir. Basit HTTPS `GET` ve JSON servisleri mevcut HTTP adaptörüyle; XML,
OAuth, sayfalama veya özel dönüşüm isteyen servisler sağlayıcıya özgü adaptörle
bağlanır. Canlı çağrı ancak onaylı kanonik registry kaydı ve açık
`--confirm-live` seçeneğiyle yapılır.

Dataset üretiminde değişken canlı yanıtlar doğrudan kullanılmaz. Uygun API veya
resmî veri kaynağından alınan sonuç normalize edilir, kişisel veriden
arındırılır ve kaynak URL'si, alınma zamanı, lisans, sürüm ile SHA-256 özetiyle
dondurulmuş fixture'a dönüştürülür. Bu fixture yürütme sırasında `mock` olarak
çalışsa da kökeni fixture provenance açıklamasında `synthetic`, `api_snapshot`
veya `official_snapshot` olarak açıkça belirtilmelidir. Otomatik fixture yakalama
hattı eklendiğinde bu ayrım yapılandırılmış metadata alanına taşınacaktır.
Böylece gerçekçilik ile tekrar üretilebilirlik birlikte korunur.

Ölçekleme öncesindeki ana çalışma, uygun gerçek API/resmî kaynakları seçmek;
erişim ve yeniden kullanım koşullarını doğrulamak; normalizasyon adaptörlerini,
fixture yakalama akışını ve contract testlerini tamamlamaktır. API erişimi
belgelenmeyen araçlar düşük oranlı sentetik mock olarak kalır veya üretim
dağılımından çıkarılır.

## 3. Türkçe senaryo üretimi

Normal akışta blueprint dosyası doğrudan `dataset generate` komutuna verilir.
CLI bütün blueprint’leri canlı model çağrısından önce doğrular; tek job içinde
yalnızca bir kaynak türüne izin verir. Manifest, input checksum, shard,
checkpoint, hata kuyruğu, hedef dağılım ve ID planı otomatik oluşturulur.

```text
magibu-toolcall dataset generate blueprints/pilot.jsonl --registry registry/proposals/pilot_candidates.jsonl --job-id dataset-pilot-001 --max-workers 4 --token-budget 250000 --execute-live
```

`--output` verilmezse adaylar
`data/dataset/staging/<job_id>.jsonl` yoluna yazılır. İş kanıtları
`runs/dataset/<job_id>/` altında tutulur. `--start-number` verilmezse ilgili
kaynak türünün mevcut dataset kayıtları taranarak sıradaki çakışmasız numara
seçilir. Blueprint’lerdeki `source_type` yalnız `original_turkish` veya
`turkey_native` olabilir.

`--registry` verilirse yolu ve SHA-256 özeti job manifestine bağlanır. Registry
değişmiş veya kaybolmuşsa `batch run`, `batch status` ve `batch report` işi
durdurur. Aday araçlarla pilot üretirken proposal registry açıkça verilmelidir;
araçlar bu nedenle kanonik registry’ye erken taşınmaz.

Normal üretimde `deepseek-v4-flash` birincil modeldir. Geçersiz JSON, provider
hatası, zaman aşımı, Latin dışı yazı sızıntısı veya deterministik dil-planı
ihlali bütün retry'leri tüketirse aynı güvenli üretim brief’i `deepseek-v4-pro` ile bir kez
daha denenir. Birincil ve fallback çağrılarının bütçesi ayrı hesaplanır;
`provider_fallbacks_used` iş özetine, geçiş nedeni ile iki model kimliği
provenance'a yazılır. Fallback de başarısızsa kayıt hata kuyruğuna gider.
OpenAI kalite kapısından geçmeyen hiçbir kayıt otomatik kabul edilmez.

Yürütme türü, fixture kimliği, provenance, kaynak kimliği ve veri sürümü gibi
alanlar iç operasyon bilgisidir; doğal kullanıcı veya asistan cümlesi değildir.
DeepSeek'e ham blueprint verilmez. Üretimden önce yalnız kullanıcı amacı,
konuşma gereksinimi, sağlanan/eksik parametreler, son yanıt beklentisi ve
kullanıcıya gösterilebilir grounding alanlarından bir brief oluşturulur. İç
metadata anahtarları ve iç operasyon değerleri bu projeksiyonda yer almaz.

Prompt, yasaklı etiketleri tek tek modele göstermeden yalnız kullanıcı görevinde
kalmasını ve örneğin nasıl üretildiğine ilişkin implementasyon açıklaması
eklememesini ister. Model yanıtı yine deterministik olarak denetlenir. Politika
ihlali olursa sonraki deneme hatalı metni veya etiketi prompta geri taşımadan
temiz bir yeniden yazma talimatı kullanır; gerekirse Pro fallback devreye girer.
Bu kavramların gerçekten konuşulduğu bir senaryo ancak blueprint'te
`internal_marker_topic` etiketiyle açıkça işaretlenirse istisna oluşturur. Sistem
provenance gerçeğini silmez; onu eğitim diyaloğundan ayrı canonical audit kaydında
ve fixture provenance alanlarında korur.

Modelin döndürdüğü `accepted`, reviewer veya validation beyanları güvenilir kabul
edilmez. CLI bunları kanıta dayalı draft durumuna çevirir:

- Blueprint metadata’sı, exposed tool listesi, beklenen tool call ve tool result değiştirilemez.
- Provider/model kimliği ve blueprint bağlantısı provenance'a sistem tarafından yazılır.
- Provider response modeli, request ID, deneme sayısı ve token kullanımı provenance'a yazılır.
- Kayıt daima `needs_revision` başlar; insan onayı GitHub PR'da verilir.
- Çalıştırılmayan execution, semantik, dil ve tekrar kontrolleri `not_run` kalır.
- `not_run` veya `failed` bir kalite aşaması varken kayıt `accepted` olamaz.

Üretimden sonra otomatik kalite kanıtları ayrı komutla hesaplanır:

```text
magibu-toolcall dataset quality data/dataset/staging/dataset-pilot-001.jsonl data/dataset/needs_revision/dataset-pilot-001.jsonl --registry registry/proposals/pilot_candidates.jsonl --reference data/dataset/accepted/dataset.jsonl --semantic-provider openai --semantic-threshold 0.90 --judge-provider openai --judge-escalation --judge-escalation-sample-rate 0.10 --judge-max-workers 4 --confirm-live --report review/dataset/dataset-pilot-001.quality.json
```

Bu komut şema ve tool-call yapısını yeniden doğrular; local/mock çağrıları
gerçekten çalıştırıp kayıt içindeki tool result ile karşılaştırır. Exact ve
normalize tekrar kontrolü her zaman yapılır. `--semantic-provider openai`, bütün
benzersiz metinleri toplu embed eder ve yalnızca eşik üstü duplicate bulgularını
raporda tutar. Üretim embedding'i olmadan tamamlanması gereken karşılaştırmalar
varsa duplicate kapısı `not_run` kalır. `token-test-double` yalnız test içindir ve
üretim duplicate kapısını onaylayamaz.

`--judge-provider openai`, her kaydı strict JSON rubric ile bağımsız olarak
değerlendirir ve `validation.semantic` kapısını yönetir. Birincil model bütün
kayıtları inceler. `--judge-escalation` verildiğinde birincil modelin geçiremediği
kayıtlar ile geçenlerin deterministik örneklemi ikinci modele gönderilir; model
anlaşmazlığı kaydı bloke eder. Model snapshot'ları, rubric sürümü, skorlar,
request ID, token kullanımı ve system fingerprint kalite raporuna yazılır.
`--reference` dosyaları yalnızca önceden kabul edilmiş dataset kayıtları
içerebilir; aynı ID'nin yeniden kullanılması engellenir.

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
magibu-toolcall dataset batch run runs/dataset/dataset-pilot-001/manifest.json --max-workers 4 --token-budget 250000 --execute-live
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
magibu-toolcall tool run-api kurum_veri_ara --arguments "{\"query\":\"örnek\"}" --confirm-live
```

HTTP response gövdesi veya credential hata mesajına eklenmez. Sonuçlar
`passed`, `failed`, `timeout`, `rate_limited`, `empty_result` veya
`invalid_result` olarak normalize edilir.

## 5. Üretim semantik benzerlik

`token-test-double` yalnız yerel ve deterministik test içindir. Üretimde OpenAI
embedding modeli açıkça yapılandırılır:

```text
MAGIBU_TOOLCALL_OPENAI_API_KEY
MAGIBU_TOOLCALL_OPENAI_MODEL
MAGIBU_TOOLCALL_OPENAI_ESCALATION_MODEL
MAGIBU_TOOLCALL_OPENAI_EMBEDDING_MODEL
MAGIBU_TOOLCALL_OPENAI_BASE_URL
MAGIBU_TOOLCALL_SEMANTIC_CACHE_DIR
MAGIBU_TOOLCALL_OPENAI_DAILY_TOKEN_BUDGET
MAGIBU_TOOLCALL_OPENAI_ESCALATION_DAILY_TOKEN_BUDGET
```

```text
magibu-toolcall dataset quality data/dataset/staging/candidates.jsonl data/dataset/needs_revision/candidates.jsonl --reference data/dataset/accepted/dataset.jsonl --semantic-provider openai --semantic-threshold 0.90 --semantic-cache .cache/semantic --judge-provider openai --judge-escalation --judge-escalation-sample-rate 0.10 --judge-max-workers 4 --confirm-live

magibu-toolcall benchmark contamination-check --benchmark data/benchmark/staging/candidates.jsonl --dataset data/dataset/accepted/dataset.jsonl --semantic-provider openai --semantic-threshold 0.90 --semantic-cache .cache/semantic --output json
```

Embedding'ler provider model kimliğine ve metin SHA-256 değerine göre önbelleğe
alınır. 1000 kayıtlık taramada her benzersiz metin bir kez toplu embed edilir;
bütün çiftler yerine yalnız duplicate bulguları kalıcı rapora yazılır. Model,
eşik, judge rubric'i ve token bütçeleri raporda sabitlenmeli ve ekip tarafından
onaylanmalıdır.

## 6. GitHub PR incelemesi ve export

İnsan onayı için CLI komutu yoktur. Aday kayıt ve kalite raporu ayrı bir branch'e
eklenir, pull request açılır ve repository şablonundaki dil, teknik, provenance,
lisans ve güvenlik maddeleri incelenir. Reviewer kimliği, değişiklik talepleri ve
onay geçmişi GitHub üzerinde kalır.

PR içinde kabul edilecek kayıtların `validation.language` alanı inceleme
sonucunda `passed`, `review.status` alanı `accepted` yapılır. Bu etiketler tek
başına yetki kanıtı değildir; güvenilir insan onayı protected branch'e birleşmiş
PR'dır. Export komutu yalnız `accepted` ve tüm validation kapıları tamamlanmış
kayıtları alır. Varsayılan canonical export tam audit kaydını korur:

```text
magibu-toolcall dataset export data/dataset/staging/pr-approved.jsonl data/dataset/accepted/dataset.jsonl
```

Modele verilecek eğitim dosyası ayrı bir projeksiyonla yalnız `id`, `messages` ve
`tools` alanlarını içerir:

```text
magibu-toolcall dataset export data/dataset/accepted/dataset.jsonl data/dataset/training/dataset.jsonl --projection training
```

Eğitim projeksiyonu iç operasyon etiketlerini modelin görebileceği alanlarda
bulursa exportu durdurur. `internal_marker_topic` ile açıkça işaretlenmiş gerçek
konu örnekleri bu kapının bilinçli istisnasıdır.

Benchmark freeze/run komutları altyapıda korunur ancak güncel çalışma odağında
değildir ve bu aşamada kullanılmaz.

## Dizinler

- `schemas/`: Dataset, benchmark, registry, blueprint, source work item ve batch job sözleşmeleri
- `registry/`: Kanonik tool kayıtları ve deterministik fixture’lar
- `blueprints/`: Dataset ve benchmark için ayrı üretim blueprint’leri
- `data/dataset/`: `raw`, `staging`, `needs_revision`, `rejected`, `accepted`
- `data/benchmark/`: Ayrı lifecycle ve ek olarak immutable `gold`
- `review/`: Otomatik kalite raporları ve PR incelemesini destekleyen kanıtlar
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
MAGIBU_TOOLCALL_DEEPSEEK_FALLBACK_MODEL
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

Gerçek secret değerleri `.env.example`, registry, manifest, kalite raporu, hata kuyruğu
veya test fixture’larına yazılmamalıdır.

## Doğrulama

```text
.venv/Scripts/python -m pytest
powershell -File scripts/verify.ps1
```

Testler canlı API çağrısı yapmaz. HTTP ve provider testleri enjekte edilmiş
taşıyıcılarla request/response, timeout, rate-limit, invalid JSON, secret
redaction, cache ve retry davranışlarını doğrular. Canlı üretim ancak ilgili
credential ve açık `--execute-live`/`--confirm-live` seçeneğiyle başlatılır.

Sonraki güvenli adım, `main` branch protection ayarlarını etkinleştirmek; 30 pilot
kaydı GitHub PR üzerinden insan incelemesinden geçirmek ve bulgulara göre ikinci
pilot blueprint sürümünü hazırlamaktır. xLAM/When2Call ve benchmark çalışmaları
askıda kalır.
