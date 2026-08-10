# Kalite kanıtları ve PR incelemesi

[← Dokümantasyon merkezi](../docs/README.md) · [Katkı rehberi](../CONTRIBUTING.md)

Bu klasör, GitHub pull request'e özellikle seçilerek eklenen otomatik kalite
raporlarını içerir. Ham provider cevapları, yerel çalışma logları ve reviewer
kimlik bilgileri burada tutulmaz.

Dataset katkısı için izlenebilir dosya adları:

```text
data/dataset/needs_revision/<job_id>.pr.review.jsonl
review/dataset/<job_id>.pr.quality.json
```

İki dosya aynı `job_id` değerini kullanmalıdır. Aday kayıt olmadan kalite raporu,
kalite raporu olmadan dataset katkısı eksik inceleme paketi sayılır.

## PR inceleme akışı

1. Katkı ayrı bir branch'te hazırlanır.
2. `Contribution guidance`, PR açıklamasını ve değişen dosya adlarını okuyarak tek
   bir rehber yorum oluşturur veya mevcut yorumunu günceller.
3. `Pull request validation` içindeki `validate` işi PR branch'ini checkout eder;
   testleri ve yapılandırılmış sözleşmeleri çalıştırır.
4. İnsan reviewer Türkçe, tool seçimi, argümanlar, grounding, provenance, lisans,
   güncellik ve güvenlik sınırlarını inceler.
5. Düzeltmeler aynı PR'a eklenir. Son commit üzerindeki kontroller ve gerekli
   onaylar tamamlandığında değişiklik `main` branch'ine alınır.

Katkı rehberi botunun başarılı çalışması, PR'ın kabul edildiği anlamına gelmez.
Bot şablon eksiklerini ve dosya paketiyle ilgili uyarıları yorum olarak bildirir;
otomatik düzeltme, commit, approval veya merge yapmaz. Teknik geçerliliğin kaynağı
`validate`, nihai kararın kaynağı insan incelemesidir.

`Contribution guidance`, güvenlik nedeniyle `pull_request_target` üzerinde ve
yalnız default branch'teki workflow tanımıyla çalışır. Workflow'u ilk kez ekleyen
PR'da bot yorumu görülmeyebilir; değişiklik `main` ile birleştirildikten sonra
açılan veya güncellenen PR'larda devreye girer. Workflow katkı branch'ini checkout
etmez ve katkı kodunu çalıştırmaz.

Kaydın `metadata.review.status` alanı yalnız yaşam döngüsü etiketidir. Güvenilir
reviewer kimliği, zaman damgaları, yorumlar ve approval/change-request geçmişi
GitHub PR geçmişinde tutulur. CLI reviewer hesabı, rolü veya access-policy dosyası
istemez ve GitHub approval durumunu API üzerinden doğrulamaz.

Repository yöneticileri `main` için en az şu kuralları etkinleştirmelidir:

- pull request zorunluluğu;
- en az bir bağımsız onay;
- yeni commit'te eski onayların düşürülmesi;
- konuşmaların çözülmesi;
- `validate` durum kontrolünün zorunlu olması;
- doğrudan push, force-push ve branch silmenin engellenmesi.
