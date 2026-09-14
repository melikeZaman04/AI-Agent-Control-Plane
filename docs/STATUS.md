# Architect OS — Güncel Durum

**Güncelleme tarihi:** 2026-09-15 (Europe/Istanbul)

**Aktif dal:** `main`

**Checkpoint:** M2.3b, A2 protokolü ve M3 tamamlanması. Kesin commit kimliği için `git log -1 --oneline`.

## Özet

**M3 Project Chronicle üst kilometre taşı tamamlandı.** M2.3b, A2 protokolü ve
M3 değişiklikleri kullanıcı onayıyla bu Git checkpoint’ine dahil edildi. Push
yapılmadı. Sıradaki M4 için ayrıntılı kapsam ve çıkış kriterleri henüz tanımlı değil. M2.4 Passive Observer ertelenmiş durumda.

| Aşama | Durum |
|---|---|
| M0 / M1 / M2.1 / M2.2 / M2.3a | COMPLETE |
| M2.3b — Live Codex OTel | COMPLETE |
| M2.4 — Passive Observer | DEFERRED |
| M3.1 — Chronicle Foundation | COMPLETE |
| M3.2 — CLI ve kanıt inceleme | COMPLETE |
| M3.3 — Git ve ADR geçmişi | COMPLETE |
| M3.4 — Çalışma makbuzları ve hata geçmişi | COMPLETE |
| M3.5 — Üst kilometre taşı doğrulaması | COMPLETE |
| M4 — Session Intelligence | NOT STARTED, insan onayı gerekiyor |

## Kullanılabilir geçmiş

`architect chronicle --view` ile episodes, changes, decisions, receipts,
automations ve failures sorgulanabilir; `--json` deterministik çıktı verir.
Git/ADR kayıtları commit/path/blob kaynaklarına, makbuzlar run/event kanıtlarına
bağlıdır. Git commit'leri kanıt olmadan run'lara atfedilmez. Araç onayları kalıcı
proje kararı değildir. Otomasyon için açık lifecycle metadata işareti gerekir;
mevcut provider entegrasyonları bu işareti üretmiyor. Ayrıntılar ADR-005'tedir.

## Doğrulama ve sınırlar

M3 kapanışında 25 yeni test vakası eklendi. Tam regresyon sonucu:
**201 passed in 1.28s** (loopback erişimiyle). Git diff/whitespace kontrolleri temiz.
Gerçek Git depoları, SQLite, FlightRecorder, Claude/Codex normalizasyonu ve CLI
kaynak çözümlemeleri test edildi. Yeni şema/bağımlılık/scheduler/LLM eklenmedi.
Git geçmişi seçili revision'dan erişilebilir yerel commit'lerle sınırlıdır;
çalışma ağacı değişiklikleri ve M4 doğal dil zekâsı kapsam dışındadır.

Önceki 136 testlik M2.3b paketi, 158 testlik M3.1 ve 176 testlik M3.2 kabul
kanıtları ilgili raporlarda korunuyor. Yeni dış provider smoke oturumu yapılmadı.

M3 kapsamı için Gate G bildirildi ve insanın açık kapanış sözleşmesiyle çözüldü.
A2 kapsamında tüm M3.x işleri arasında otomatik ilerleme uygulandı. Çözülmemiş
karar kapısı yok; M4 başlatılmadı. Kod veya Git geçmişi silinmedi/geri alınmadı.

Kabul kanıtı: [milestones/M3.md](milestones/M3.md).
Kanonik kapsam: [ROADMAP.md](ROADMAP.md).
