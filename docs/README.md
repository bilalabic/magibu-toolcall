# Dokümantasyon merkezi

Bu sayfa `magibu-toolcall` dokümantasyonunun ana navigasyonudur. Belgeler kullanım
amacına göre ayrılır; aynı kuralın birden fazla dosyada farklı biçimde tutulması
yerine her konu için tek bir ana kaynak kullanılır.

## Nereden başlamalıyım?

| Okuyucu | İlk belge | Sonraki adım |
| --- | --- | --- |
| Projeyi tanımak isteyen | [Ana README](../README.md) | [Mimari](architecture.md) |
| CLI'ı çalıştıracak geliştirici | [Teknik kullanım rehberi](../README_TEKNIK.md) | [Validation](validation.md) |
| Katkı hazırlayacak geliştirici | [Katkı rehberi](../CONTRIBUTING.md) | Katkı türüne göre aşağıdaki ilgili belge |
| Dataset küratörü/reviewer | [Dataset yaşam döngüsü](../data/dataset/README.md) | [Review alanı](../review/README.md) |
| Tool/API araştırmacısı | [Tool proposal şablonu](tool_proposal_template.md) | [Execution ortamları](execution_environments.md) |
| Proje yöneticisi | [Bilinen sınırlamalar](known_limitations.md) | [Sonraki aşama kontrol listesi](next_stage_checklist.md) |

## Rehberler

Bir işi adım adım yapmak için kullanılır.

- [Teknik kullanım rehberi](../README_TEKNIK.md): kurulum, yapılandırma, tek kayıt
  testi, kalite kontrolü, toplu üretim ve export.
- [Katkı rehberi](../CONTRIBUTING.md): PR paketi, tool/blueprint/dataset katkısı
  ve yerel kontroller.
- [Dataset yaşam döngüsü](../data/dataset/README.md): staging, review, accepted ve
  training projection akışı.
- [Benchmark yaşam döngüsü](../data/benchmark/README.md): dataset'ten izolasyon,
  kontaminasyon ve freeze sınırları.
- [Review alanı](../review/README.md): kalite raporu dosyaları ve GitHub inceleme
  akışı.

## Kavramlar ve mimari

Sistemin neden bu şekilde tasarlandığını açıklar.

- [Architecture](architecture.md): modüller, veri akışı ve güven sınırları.
- [Execution environments](execution_environments.md): local, mock,
  fully-simulated, real API ve sandbox ayrımı.
- [Scenario blueprints](scenario_blueprints.md): scenario oracle'ı, kategori
  önceliği ve authoring kuralları.
- [Validation](validation.md): deterministik pipeline, diagnostic kodları, model
  ve insan doğrulama katmanları.

## Referanslar

Kararlı isimleri, formatları ve katkı sözleşmelerini tanımlar.

- [Versioning and IDs](versioning.md)
- [Tool proposal template](tool_proposal_template.md)
- JSON Schema sözleşmeleri: [`schemas/`](../schemas/)
- CLI referansı: `magibu-toolcall --help` ve alt komutların `--help` çıktıları

## Proje durumu ve kararlar

Bugünkü kapasiteyi, riskleri ve ölçekleme kapılarını izlemek için kullanılır.

- [Known limitations](known_limitations.md)
- [Next-stage checklist](next_stage_checklist.md)
- [Risk register](risk_register.md)
- [Dependency decisions](dependency_decisions.md)

## Araştırma

- [Tool-calling dataset coverage research](tool_call_dataset_coverage_research.md)
- [AFAD canlı API değerlendirmesi](afad_endpoint_revalidation.md)

Araştırma belgesi gelecekteki `0.2.x` önerilerini de içerir. Uygulanmış davranış
için teknik rehber, `--help` çıktısı, mevcut şemalar ve bilinen sınırlamalar esas
alınır.

## Bilginin ana kaynağı

| Soru | Kaynak |
| --- | --- |
| Proje bugün ne yapabiliyor? | Ana README + `known_limitations.md` |
| Bir komut nasıl çalıştırılır? | Teknik README + CLI `--help` |
| Katkıda hangi dosyalar gerekir? | `CONTRIBUTING.md` |
| Veri hangi klasöre yazılır? | `data/` altındaki README'ler |
| Bir alan yapısal olarak geçerli mi? | `schemas/` altındaki JSON Schema |
| Modüllerin güven sınırı nedir? | `architecture.md` + `execution_environments.md` |
| Gelecekte ne öneriliyor? | Araştırma, risk ve next-stage belgeleri |

## Dokümantasyon kuralları

Belge karmaşasını önlemek için:

1. Ana README proje tanıtımı ve güncel kapsam dışında ayrıntıya girmez.
2. Çalıştırılabilir komutlar teknik README'de tutulur ve CLI `--help` ile
   doğrulanır.
3. Katkı zorunlulukları yalnız `CONTRIBUTING.md` içinde normatif olarak tanımlanır.
4. Klasöre özgü dosya politikaları ilgili klasörün README'sinde tutulur.
5. Uygulanmış özellik ile araştırma önerisi açıkça ayrılır.
6. Kullanıcıya yönelik README'ler Türkçe; kararlı machine alanları İngilizce
   kalır.
