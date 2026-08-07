# Benchmark yaşam döngüsü

Bu alan eğitim veri kümesinden bağımsız benchmark kayıtlarını içerir. Benchmark
kimlikleri kaynak türüne göre `bench_tr_*`, `bench_ot_*` veya `bench_tn_*`
biçimindedir.

- `raw/`: Benchmark ekibinin değiştirilmemiş kaynak girdileri.
- `staging/`: Doğrulama ve bağımsız inceleme bekleyen gold adayları.
- `needs_revision/`: Düzeltilmesi gereken gold adayları.
- `rejected/`: Kabul edilmeyen benchmark kayıtları.
- `accepted/`: İnceleme ve doğrulama kapılarını geçmiş kayıtlar.
- `gold/`: Checksum manifestiyle dondurulmuş resmî benchmark sürümleri.

Benchmark kayıtları eğitim verisine eklenmez. Model tahminleri gold dosyasına
yazılmaz ve yalnızca `runs/` altında saklanır. `benchmark freeze`, dataset
snapshot yolunu zorunlu tutar; kontaminasyon kapısı geçmeden gold ve manifest
oluşturmaz.

Benchmark üretim job’ları yalnız benchmark kapsamlı principal tarafından
`benchmark_generation` manifestiyle çalıştırılır. Dataset job manifesti,
checkpoint’i veya ID aralığı benchmark hattında kullanılamaz. Önerilen geçici iş
yolu `staging/jobs/<job_id>/` biçimindedir.
