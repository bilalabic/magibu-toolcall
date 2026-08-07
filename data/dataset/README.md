# Dataset yaşam döngüsü

Bu alan yalnızca eğitim veri kümesi kayıtlarını içerir. Dataset kimlikleri kaynak
türüne göre `tctr_tr_*`, `tctr_ot_*` veya `tctr_tn_*` biçimindedir.

- `raw/`: Değiştirilmemiş kaynak kayıtları.
- `staging/`: Doğrulama ve inceleme bekleyen adaylar.
- `needs_revision/`: Düzeltilmesi gereken kayıtlar.
- `rejected/`: Kabul edilmeyen kayıtlar.
- `accepted/`: Yalnızca doğrulanmış ve insan incelemesinden geçmiş dışa aktarımlar.

Dataset kayıtları benchmark gold alanına kopyalanmaz.

xLAM/When2Call içe aktarma kayıtları kanonik dataset değildir; `raw/` altında
source work item olarak tutulur. Lokalizasyon ve üretim job manifestleri için
önerilen yer `staging/jobs/<job_id>/` yoludur. CLI gerekli klasörleri iş
oluşturulurken açar; boş job klasörleri depoda tutulmaz. Checkpoint part dosyaları
tamamlanan işin yeniden başlatma ve audit kanıtıdır.
