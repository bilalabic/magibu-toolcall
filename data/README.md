# Veri alanları

[← Dokümantasyon merkezi](../docs/README.md)

Bu dizin üç ayrı alanı barındırır:

| Alan | Kimlik öneki | Kullanım | Aktif durum |
| --- | --- | --- | --- |
| [`dataset/`](dataset/README.md) | `tctr_*` | Eğitim veya ince ayar kayıtları | Aktif |
| [`benchmark/`](benchmark/README.md) | `bench_*` | Eğitim verisine girmeyen değerlendirme gold kayıtları | Üretim askıda |
| `snapshots/` | `<snapshot_version>` | `local_executable` tool'ların okuduğu sürümlenmiş kaynak snapshot'ları | Aktif |

`snapshots/` ilk ikisinden farklı bir şeydir: dataset kaydı değil, tool'ların
çalışma zamanında okuduğu sabitlenmiş kaynak veridir. Her snapshot kendi
dizininde `provenance.json`, ham kaynak dosyalarının bulunduğu `raw/` ve
üretilmiş veri dosyasını taşır. Ham dosyalar bilerek commit edilir; snapshot'ın
denetlenebilirliği onlara dayanır. Provenance kaydı
[`schemas/snapshot_provenance.schema.json`](../schemas/snapshot_provenance.schema.json)
ile doğrulanır ve ham dosya başına `sha256` zorunludur, yani beyan edilen bayt
ile commit edilen bayt her PR'da karşılaştırılır.

```powershell
.\.venv\Scripts\python.exe -m tool_call_tr.snapshots data\snapshots
```

Dizin düzeni, alan anlamları ve dönüştürme scripti kuralı
[execution ortamları belgesinde](../docs/execution_environments.md) açıklanır.

Dataset ve benchmark aynı şema sürümünü, Tool Registry'yi ve kategori
taksonomisini paylaşabilir; fakat aynı kayıt iki alana birden kopyalanmaz.
Benchmark çalışması yeniden açıldığında benzerlik, zorunlu dataset snapshot'ı
üzerinden `benchmark contamination-check` ve `benchmark freeze` komutlarıyla
denetlenir.

Model tahminleri ile job çalışma kanıtları canonical veri değildir ve bu dizine
yazılmaz:

- dataset manifest, checkpoint ve hataları: `runs/dataset/<job_id>/`
- benchmark model tahminleri: `runs/<model_name>/<run_id>.jsonl`
- PR'a seçilen otomatik kalite raporları: `review/dataset/`

Kaynak importları, lokalizasyon iş kayıtları ve batch checkpoint'leri operasyonel
çıktılardır; `accepted` dataset veya benchmark yerine geçmez. Her batch manifesti
tek bir yaşam döngüsüne bağlanır.

Güncel geliştirme odağı `original_turkish` ve `turkey_native` dataset
kayıtlarıdır. Çeviri/lokalizasyon ve benchmark aday üretimi şimdilik askıdadır.
