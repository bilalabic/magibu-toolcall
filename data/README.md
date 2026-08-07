# Veri alanları

Bu dizinde eğitim veri kümesi ile benchmark fiziksel olarak ayrı tutulur.

- `dataset/`: Eğitim veya ince ayar için hazırlanacak `tctr_*` kayıtlarının yaşam döngüsü.
- `benchmark/`: Eğitim verisine eklenmeyecek `bench_*` gold kayıtlarının bağımsız yaşam döngüsü.

Dataset ve benchmark aynı şema sürümünü, Tool Registry'yi ve kategori taksonomisini
paylaşabilir; kayıt içerikleri birbirine kopyalanmaz. İki alan arasındaki benzerlik
`magibu-toolcall benchmark contamination-check` ile kontrol edilir.

Model tahminleri ve job çalışma kanıtları bu dizine yazılmaz. Dataset üretim
manifest/checkpoint/hata kayıtları `runs/dataset/<job_id>/`, benchmark çalışma
çıktıları ise `runs/<model_name>/<run_id>.jsonl` altında tutulur.

Kaynak importları, lokalizasyon iş kayıtları ve batch checkpoint’leri geçici
operasyonel çıktılardır; kanonik `accepted` dataset/benchmark biçiminin yerine
geçmez. Her batch manifesti tek bir lifecycle’a bağlıdır.

Güncel çalışma odağı `dataset/` içindeki `original_turkish` ve `turkey_native`
kayıtlarıdır. Çeviri-lokalizasyon ve benchmark üretimi şimdilik askıdadır.
