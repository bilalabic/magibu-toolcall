# Dataset yaşam döngüsü

Bu alan yalnızca eğitim veri kümesi kayıtlarını içerir. Dataset kimlikleri kaynak
türüne göre `tctr_tr_*`, `tctr_ot_*` veya `tctr_tn_*` biçimindedir.

- `raw/`: Değiştirilmemiş kaynak kayıtları.
- `staging/`: Doğrulama ve inceleme bekleyen adaylar.
- `needs_revision/`: Düzeltilmesi gereken kayıtlar.
- `rejected/`: Kabul edilmeyen kayıtlar.
- `accepted/`: Yalnızca doğrulanmış ve insan incelemesinden geçmiş dışa aktarımlar.

Dataset kayıtları benchmark gold alanına kopyalanmaz.

xLAM/When2Call çeviri-lokalizasyon hattı şimdilik askıdadır. Aktif üretim hattı
`original_turkish` ve `turkey_native` blueprint’lerinden review bekleyen dataset
adayları üretir.

Normal `dataset generate` komutu adayları `staging/<job_id>.jsonl`, manifest ve
checkpoint kanıtlarını ise `runs/dataset/<job_id>/` altında oluşturur. Model
çıktısı doğrudan kabul edilmez; tamamlanmamış kalite kontrolleri `not_run` ve
review durumu `needs_revision` olarak tutulur. Boş job klasörleri depoda tutulmaz.

`dataset quality`, otomatik execution, toplu embedding tabanlı duplicate ve
OpenAI structured-output kalite judge kanıtlarını yeniden hesaplayıp kayıtları
`needs_revision/` altında yazar; ayrıntılı rapor `review/` alanında tutulur.
Birincil judge bütün kayıtları, escalation judge ise başarısız/belirsiz kayıtlar
ile geçenlerin belirlenmiş örneklemini denetler. İnsan dil ve gerektiğinde teknik
reviewer kararları ayrı olmadan kayıt `accepted/` alanına geçirilemez.

1000 kayıt tek kontrolsüz çağrı olarak çalıştırılmaz. Önce 30, sonra 100 ve 250
kayıtlık kapılar geçilir; tam üretim dört adet 250 kayıtlık run olarak yürütülür.
Her run ayrı manifest, checkpoint, hata dosyası, token bütçesi ve kalite raporu
taşır.
