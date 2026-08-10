# Küçük uçtan uca pilot günlüğü

Bu belge, `pilot/small-e2e-20260810` dalındaki geçici dataset pilotunun işlem
günlüğüdür. Pilot `main`e alınmak veya kabul edilmiş dataset olarak yayımlanmak
için hazırlanmadı. İnsan incelemesi tamamlandıktan sonra dal ve pilot varlıkları
kaldırılacaktır.

## Kapsam

| Alan | Değer |
| --- | --- |
| Kaynak türü | `original_turkish` |
| Tool | 2 adet `local_executable` candidate |
| Blueprint | 5 kayıt; beş ana kategorinin her birinden bir adet |
| Üretim | DeepSeek Flash-first, Pro fallback |
| Otomatik kalite | OpenAI embedding, mini judge, tam-model escalation |
| Nihai pilot kayıtları | `tctr_ot_000012`–`tctr_ot_000016` |

## İşlem günlüğü

1. DeepSeek Flash/Pro, OpenAI mini/tam judge ve embedding modelleri canlı
   provider preflight ile doğrulandı.
2. Yüzde hesabı ve hız birimi dönüşümü için iki registry kaydı, iki fixture,
   deterministik local executor ve beş blueprint oluşturuldu.
3. İlk blueprint doğrulaması, izin verilmeyen `tool_necessity` secondary tag'ini
   reddetti. Etiket kaldırıldı ve beş blueprint şemadan geçti.
4. Repository test paketi pilot testleriyle birlikte 204/204 geçti.
5. V1 üretiminde 5/5 kayıt oluştu. OpenAI kalite kontrolünde tam model,
   multi-tool kaydını gereksiz tool kullanımı nedeniyle reddetti. İnsan ön
   incelemesi ayrıca eksik-parametre kaydında kullanıcı/asistan rol tersliği ve
   no-tool oracle'ında gereksiz kısıtlama buldu.
6. Blueprint'ler revize edildi. V2 ilk denemesi mevcut `000001`–`000005` kayıtları
   nedeniyle ID collision kapısında üretim başlamadan durdu; yeni aralık seçildi.
7. V2 üretiminde 5/5 kayıt oluştu. Mini judge rol tersliğini geçirdi, tam-model
   escalation aynı kaydı reddetti. Sorunun iki üretimde tekrarlanması üzerine
   generation prompt'unda genel altyapı eksikliği doğrulandı.
8. Tek turlu eksik-parametre senaryolarında ilk mesajın kullanıcının eksik isteği
   olmasını zorunlu kılan prompt düzeltmesi ve regresyon testi eklendi. Düzeltme
   pilot varlıklarından ayrı `8d63bb2` commit'inde tutuldu.
9. Tek kayıtlık canlı üretim, rol düzeltmesini doğruladı. Ana beşli set yeni
   checksum ve `000012`–`000016` ID aralığıyla baştan üretildi.
10. Final kalite çalışmasında 5/5 model pass, 0 otomatik failure, 0 duplicate ve
    4/4 uygulanabilir execution pass elde edildi. Beş kayıt da insan dil
    incelemesi için `needs_revision` durumunda bırakıldı.

## Final kalite özeti

| Ölçüm | Sonuç |
| --- | --- |
| Kayıt | 5 |
| Execution pass | 4/4 uygulanabilir kayıt |
| Model judge pass | 5/5 |
| Semantic karşılaştırma | 10 çift |
| Duplicate | 0 |
| Çince karakter | 0 |
| Doğal mesajlarda iç operasyon etiketi | 0 |
| İnsan language gate | 5 kayıt bekliyor |
| Review lifecycle | 5 kayıt `needs_revision` |

## Token notu

V1, V2, tek kayıtlık doğrulama ve final üretimin toplam DeepSeek kullanımı 10.509
provider token'dır; fallback kullanılmadı. Üç OpenAI kalite turunun judge
kullanımı toplam 28.836 token'dır. Embedding token sayısı mevcut kalite raporunda
ayrı alan olarak yayımlanmadığından bu toplama dahil değildir.

## Review paketi

- `data/dataset/needs_revision/small-e2e-pilot-20260810-final.pr.review.jsonl`
- `review/dataset/small-e2e-pilot-20260810-final.pr.quality.json`

V1 ve V2 staging, run, review ve quality çıktıları yalnız yerel audit kanıtıdır;
nihai PR paketine dahil edilmez.
