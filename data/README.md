# Veri alanları

[← Dokümantasyon merkezi](../docs/README.md)

Bu dizin iki ayrı veri yaşam döngüsünü barındırır:

| Alan | Kimlik öneki | Kullanım | Aktif durum |
| --- | --- | --- | --- |
| [`dataset/`](dataset/README.md) | `tctr_*` | Eğitim veya ince ayar kayıtları | Aktif |
| [`benchmark/`](benchmark/README.md) | `bench_*` | Eğitim verisine girmeyen değerlendirme gold kayıtları | Üretim askıda |

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
