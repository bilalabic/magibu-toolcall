# Kalite kanıtları

Bu klasör otomatik kalite raporları ve incelemeyi destekleyen kanıtlar içindir.
Reviewer kimliği, rolü veya giriş bilgisi burada tutulmaz.

İnsan incelemesi GitHub pull request üzerinden yürütülür:

1. Katkı ayrı bir branch üzerinde hazırlanır.
2. `dataset validate`, kalite kontrolleri ve GitHub Actions doğrulaması çalışır.
3. Reviewer Türkçe, tool seçimi, argümanlar, sonuç grounding'i, provenance,
   lisans ve güvenlik kontrollerini PR üzerinde yapar.
4. Gerekli düzeltmeler aynı PR'a eklenir.
5. Zorunlu kontrol ve PR onayı tamamlanınca değişiklik `main` branch'ine alınır.

Kayıttaki `review.status` yalnız yaşam döngüsü etiketidir. Güvenilir reviewer
kimliği ve karar geçmişinin kaynağı GitHub PR geçmişidir. CLI kullanıcı hesabı,
reviewer rolü, access-policy dosyası veya ayrı audit girişi istemez.

Repository ayarlarında `main` için branch protection etkinleştirilmeli; pull
request, en az bir onay, güncel branch ve `validate` durum kontrolü zorunlu
olmalıdır. Eski onayların yeni commit geldiğinde düşürülmesi önerilir.
