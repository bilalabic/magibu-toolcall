# İnceleme kararları

Dataset ve benchmark inceleme kararları birbirinden ayrı tutulur:

- `dataset/`: `tctr_*` kayıtlarına ait dil ve teknik inceleme kararları.
- `benchmark/`: `bench_*` kayıtlarına ait bağımsız gold inceleme kararları.

İnceleme kararları CLI ile uygulanırken giriş kaydı doğrudan değiştirilmez; açıkça
belirtilen yeni bir çıktı dosyası oluşturulur.

Üretim CLI komutları reviewer/operator kimliğini access-policy dosyasından
doğrular. Dataset principal’ı benchmark kapsamında işlem yapamaz. Başarılı ve
engellenen yetkilendirme kararları ilgili lifecycle altında JSONL audit kaydına
yazılır; her olay önceki olayın SHA-256 değerini içerir. Zincir
`magibu-toolcall access verify-audit` ile doğrulanır. Bu uygulama kontrolü,
benchmark klasörleri için işletim sistemi veya nesne depolama ACL’inin yerine
geçmez.
