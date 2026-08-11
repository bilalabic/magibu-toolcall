# AFAD deprem verisi için canlı API değerlendirmesi

## Mevcut durum

- İnceleme tarihi: 2026-08-11
- Canlı erişim: Beklemede (`HOLD`)
- Desteklenen çalışma türü: `mock`
- Araçlar:
  - `earthquake.list_recent.v1`
  - `earthquake.get_event_details.v1`

## İnceleme sonucu

AFAD'ın resmî [Event Web Service](https://deprem.afad.gov.tr/event-service) ve
[deprem kataloğu](https://deprem.afad.gov.tr/event-catalog) sayfalarına
erişilebiliyor. Ancak güvenilir ve tekrarlanabilir bir canlı bağlantı için gereken
şu bilgiler doğrulanamadı:

- Depremleri listelemek ve olay ayrıntılarını almak için kullanılacak resmî uç noktalar
- Kabul edilen sorgu parametreleri ile JSON yanıtlarının yapısı
- Tarih ve saat bilgilerinin UTC veya Türkiye saati olarak nasıl döndürüldüğü
- Zaman aşımı, istek sınırı ve hata yanıtlarının nasıl ele alındığı
- Gerçek API yanıtlarının test verisi olarak saklanma ve yeniden dağıtılma koşulları

Bu bilgiler doğrulanana kadar AFAD'a canlı istek gönderilmeyecek ve belgelenmemiş
uç noktalar kullanılmayacaktır.

## Alternatif kaynaklar

| Kaynak | Sunduğu olanak | Değerlendirme |
| --- | --- | --- |
| [EMSC](https://www.seismicportal.eu/fdsn-wsevent.html) | JSON yanıtı, FDSN `query` ve `eventid`; CC BY 4.0 | Canlı kullanım için ilk aday |
| [USGS](https://earthquake.usgs.gov/fdsnws/event/1/wsdl) | GeoJSON yanıtı, FDSN `query` ve `eventid` | İkinci aday |
| [GFZ/GEOFON](https://geofon.gfz.de/waveform/webservices/fdsnws.php) | FDSN `query` ve `eventid`; QuakeML veya metin yanıtı | Ek bir ayrıştırıcı gerektirdiği için düşük öncelikli |
| [Kandilli](https://www.koeri.boun.edu.tr/scripts/sondepremler.asp) | Belgelenmiş JSON veya FDSN API'si bulunmuyor | API kaynağı olarak kullanılmayacak |

## Proje kararı

1. İki AFAD aracı yalnızca `mock` çalışma türünü destekleyecek; canlı kullanım
   beklemede kalacak.
2. Aşağıdaki sürümlü ve sentetik test verileri kullanılacak:
   - `earthquake.afad.list_recent.v1`
   - `earthquake.afad.event_details.v1`
3. Canlı bağlantı için bir deneme yapılması gerekirse önce EMSC değerlendirilecek.
4. Bir kaynak başarısız olduğunda başka bir kaynağa otomatik ve açıklamasız geçiş
   yapılmayacak.
5. Sonuçtaki `source` alanı gerçek veri kaynağını gösterecek; EMSC veya USGS verisi
   AFAD verisi olarak etiketlenmeyecek.

## Canlı kullanımın açılma koşulları

- [ ] Resmî uç noktalar ve kabul edilen parametreler doğrulandı.
- [ ] Liste ve olay ayrıntısı yanıt örnekleri kaydedildi.
- [ ] UTC ile Türkiye saati arasındaki dönüşüm test edildi.
- [ ] Liste sonucundaki olay kimliğiyle ayrıntı sorgusu arasındaki bağlantı test edildi.
- [ ] Boş sonuç, 4xx, 429, 5xx ve zaman aşımı durumları için testler yazıldı.
- [ ] Lisans, atıf ve gerçek API yanıtlarını saklama koşulları onaylandı.
- [ ] Sağlayıcı yanıtının ortak çıktı şemasına dönüştürülmesi test edildi.
- [ ] İnsan incelemesi tamamlandı.

Bu koşullar tamamlanmadan registry kayıtlarına `real_api` veya `execution.http`
eklenmemelidir.
