# Benchmark yaşam döngüsü

[← Veri alanları](../README.md) · [Dokümantasyon merkezi](../../docs/README.md)

Bu klasör eğitim dataset'inden bağımsız değerlendirme kayıtları içindir.
Benchmark üretimi şu anda askıdadır; burada açıklanan akış mevcut doğrulama,
kontaminasyon, freeze, run ve report altyapısının sınırlarını gösterir.

Kimlikler kaynak türüne göre `bench_tr_*`, `bench_ot_*` veya `bench_tn_*`
biçimindedir.

## Klasörlerin anlamı

- `raw/`: Değiştirilmemiş benchmark kaynak girdileri.
- `staging/`: Doğrulama ve bağımsız inceleme bekleyen gold adayları.
- `needs_revision/`: Düzeltilmesi gereken adaylar.
- `rejected/`: Kabul edilmeyen benchmark kayıtları.
- `accepted/`: İnceleme ve doğrulama kapılarını geçmiş kayıtlar.
- `gold/`: Checksum manifestiyle dondurulmuş resmî benchmark sürümleri.

## Dataset'ten ayrım

- Benchmark kayıtları eğitim dataset'ine eklenmez.
- Dataset kayıtları benchmark gold alanına kopyalanmaz.
- Model tahminleri gold dosyasını değiştirmez; yalnız `runs/` altında tutulur.
- Benchmark gold adayları dataset snapshot'ına karşı kontaminasyon kontrolünden
  geçmeden dondurulamaz.
- Dataset ve benchmark job manifestleri, checkpoint'leri ve ID aralıkları
  birbirinin yerine kullanılamaz.

`benchmark freeze`, kabul edilmiş dataset snapshot yolunu zorunlu tutar. Exact ve
normalize kontaminasyon sonuçları engelleyicidir; semantic karşılaştırmanın
üretim kanıtı sayılabilmesi için OpenAI embedding provider'ı yapılandırılmalıdır.
Başarılı freeze, gold dosyasıyla birlikte checksum manifesti üretir.

## Askıdaki bölüm

CLI'da benchmark namespace'i görünür durumdadır; doğrulama, kontaminasyon,
dondurma, freeze doğrulama, model run ve raporlama komutları kullanılabilir.
`benchmark generate` ise aday üretimi yeniden onaylanana kadar çalışma zamanında
engellenir. Gelecekteki üretim işleri dataset'ten ayrı branch/PR, kaynak ailesi ve
insan incelemesiyle yürütülmelidir.

Teknik sınırlar için [ana teknik rehbere](../../README_TEKNIK.md) bakın.
