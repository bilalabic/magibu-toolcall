# Kalite ve PR inceleme alanı

Bu klasör commit edilmesi özellikle seçilen otomatik kalite raporlarını içerir.
Yerel geçici provider çıktıları ve reviewer kimlik bilgileri burada tutulmaz.

İnsan incelemesi GitHub pull request üzerinde yürütülür:

1. Katkı ayrı bir branch’te hazırlanır.
2. Normal CI, PR kodunu salt-okunur token ile test eder.
3. `Contribution guidance` workflow’u yalnız PR açıklamasını ve değişen dosya
   adlarını denetleyip rehber yorum bırakır; PR kodunu çalıştırmaz.
4. Normal `validate` workflow’u testleri ve yapılandırılmış veri sözleşmelerini
   doğrular.
5. Reviewer Türkçe, tool seçimi, argümanlar, grounding, provenance, lisans,
   güncellik ve güvenlik sınırlarını inceler.
6. Düzeltmeler aynı PR’a eklenir; gerekli kontroller ve güncel onay tamamlandığında
   değişiklik `main` branch’ine alınır.

Dataset katkısı için izlenebilir dosya adları:

```text
data/dataset/needs_revision/<job_id>.pr.review.jsonl
review/dataset/<job_id>.pr.quality.json
```

Kaydın `metadata.review.status` alanı yaşam döngüsü etiketidir. Güvenilir reviewer
kimliği, yorumlar, timestamps ve karar geçmişinin kaynağı GitHub PR geçmişidir.
CLI reviewer hesabı, rolü veya access-policy dosyası istemez.

PR botu danışman niteliğindedir; otomatik düzeltme, commit, approval veya merge
yapmaz. Repository ayarlarında `main` için pull request, bağımsız onay, yeni
commit’te eski onayların düşmesi, konuşmaların çözülmesi ve `validate` durum
kontrolü zorunlu olmalıdır.
