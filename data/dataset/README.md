# Dataset yaşam döngüsü

[← Veri alanları](../README.md) · [Dokümantasyon merkezi](../../docs/README.md)

Bu klasör yalnız eğitim veya ince ayar amacıyla hazırlanacak dataset kayıtlarını
içerir. Kimlikler kaynak türüne göre üretilir:

| Kaynak türü | Kimlik örneği | Durum |
| --- | --- | --- |
| `translated` | `tctr_tr_000001` | Askıda |
| `original_turkish` | `tctr_ot_000001` | Aktif |
| `turkey_native` | `tctr_tn_000001` | Aktif |

## Klasörlerin anlamı

- `raw/`: Değiştirilmemiş kaynak kayıtları; Git'e eklenmez.
- `staging/`: Üretimden çıkan ve otomatik kontrol bekleyen adaylar; Git'e eklenmez.
- `needs_revision/`: İnsan incelemesine sunulan veya düzeltme bekleyen kayıtlar.
- `rejected/`: Kabul edilmeyen kayıtlar; varsayılan olarak yerel kalır.
- `accepted/`: Doğrulama ve insan incelemesi tamamlanan canonical dataset.

Dataset kayıtları benchmark gold alanına kopyalanmaz.

## Normal üretim akışı

```text
blueprint
  -> dataset generate
  -> staging/<job_id>.jsonl
  -> dataset quality
  -> needs_revision/<job_id>.pr.review.jsonl + kalite raporu
  -> GitHub PR insan incelemesi
  -> accepted/dataset.jsonl
  -> training projection
```

`dataset generate`, blueprint ve registry checksum'larını manifeste bağlar;
checkpoint ve hata kayıtlarını `runs/dataset/<job_id>/` altında tutar. Model
çıktısı doğrudan kabul edilmez. Yeni kayıtların review durumu `needs_revision`,
henüz çalışmayan kalite kapıları ise `not_run` olur.

`dataset quality`; execution, duplicate ve yapılandırılan model kalite
kanıtlarını yeniden hesaplar. Üretim akışında semantic duplicate ve judge
provider'ları OpenAI olarak seçilir. Komutun output yolu kullanıcı tarafından
verilir. GitHub incelemesine seçilen paket için önerilen yollar şunlardır:

```text
data/dataset/needs_revision/<job_id>.pr.review.jsonl
review/dataset/<job_id>.pr.quality.json
```

Üretim kalite politikası etkin olduğunda birincil judge bütün kayıtları inceler.
Escalation açıksa birincil non-pass kayıtları ve geçen kayıtların ayarlanmış
örneklemi ikinci model tarafından da incelenir. Bu kontroller insan onayı
değildir: dil kapısı ve review durumu GitHub PR incelemesi tamamlanana kadar
beklemede kalır. Reviewer kimliği, yorumlar ve karar geçmişi GitHub'da tutulur;
CLI giriş veya rol bilgisi istemez.

## Fixture ile veri kökeni aynı şey değildir

`mock`, execution biçimidir; fixture'ın mutlaka tamamen sentetik olduğunu
göstermez. İzin veriliyorsa gerçek API veya resmî kaynaktan alınmış bir snapshot:

- kişisel veriden arındırılarak;
- kaynak, alınma zamanı, lisans ve sürüm bilgisi eklenerek;
- checksum ile dondurularak

fixture hâline getirilebilir. Tamamen sentetik fixture da kullanılabilir. Köken
bilgisi provenance içinde `api_snapshot`, `official_snapshot` veya `synthetic`
olarak belirtilir. Yapılandırılmış fixture-origin alanının daha ayrıntılı hâli
henüz gelecek geliştirme konusudur.

`sentetik`, `mock` ve `fixture` gibi operasyon etiketleri kullanıcı/asistan
metnine yazılmaz. Doğal metin doğrulayıcıları bu sızıntıları reddeder. Yalnızca
kavramın kendisini konu alan senaryolar `internal_marker_topic` etiketiyle açıkça
muaf tutulabilir.

## Modelin gördüğü ve görmediği alanlar

Üretim provider'ı canonical blueprint'in tamamını görmez. CLI yalnız doğal dil
üretimi için gerekli, kullanıcıya açıklanabilir alanlardan güvenli bir brief
oluşturur. Tool sözleşmesi, argüman, sonuç, provenance ve kalite alanları kodun
kontrolündedir.

`dataset export` canonical audit kaydını korur. Eğitim sistemine verilecek
`id`, `messages` ve `tools` alanlarından oluşan ayrı görünüm `--projection
training` ile kullanıcı tarafından seçilen yerel bir output yoluna üretilir.

## 1.000 kayda ölçekleme

1.000 kayıt tek kontrolsüz çağrıyla üretilmez. Önce 30, 100 ve 250 kayıtlık
hazırlık kapıları değerlendirilir. Bu pilotlar ölçek kararına kanıt sağlar ve
nihai release sayımına otomatik olarak eklenmez. Sistem hazır olduğunda hedef
dataset dört ayrı 250 kayıtlık job ile üretilebilir. Her job kendi manifestini,
checkpoint'ini, hata dosyasını, token bütçesini ve kalite raporunu taşır.

Adım adım komutlar için [teknik kullanım rehberine](../../README_TEKNIK.md) bakın.
