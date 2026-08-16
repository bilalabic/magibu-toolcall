"""TCMB günlük kur bültenini iki `finance` aracının çıktı sözleşmesine çevirir.

Bu modül `finance.get_exchange_rate.v1` ve `finance.list_exchange_rates.v1`
araçlarının ortak normalizasyon katmanıdır: TCMB'nin `today.xml` belgesindeki
`Currency` düğümlerini bir kez okur, iki aracın da paylaştığı kur kaydına
dönüştürür ve mock fixture'larını bu tek kaynaktan üretir. Aynı XML sözleşmesini
kullanan başka bir katkı paketi `parse_bulletin` çıktısını doğrudan yeniden
kullanabilir.

Yalnız standart kütüphaneye bağlıdır, ağ çağrısı yapmaz ve aynı girdi için her
çalıştırmada bayt bayt aynı dosyaları üretir.

Fixture'ları yeniden üretmek için:

    python scripts/fixtures/finance_tcmb.py --write
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ElementTree


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BULLETIN_FILE = Path(__file__).resolve().with_name("finance_tcmb_bulletin.xml")
FIXTURE_DIR = REPOSITORY_ROOT / "registry" / "proposals" / "fixtures"

#: Bültenin donduruldugu an. XML belgesi saat taşımadığı için sabit tutulur;
#: değişmesi fixture'ların da yeniden üretilmesini gerektirir.
RETRIEVED_AT = "2026-08-14T12:35:00Z"

#: Kur türü adı -> TCMB XML alan adı. Araçların `rate_type` enum'u budur.
RATE_TYPE_FIELDS = {
    "forex_buying": "ForexBuying",
    "forex_selling": "ForexSelling",
    "banknote_buying": "BanknoteBuying",
    "banknote_selling": "BanknoteSelling",
}

PROVENANCE = (
    "fixture_version=v1; created_at=2026-08-16T12:00:00+03:00; "
    "contract_source=https://www.tcmb.gov.tr/kurlar/today.xml; "
    "contract_verified_on=2026-08-16; data_kind=synthetic; "
    "license_review_status=pending; "
    "redistribution_status=not_applicable_to_synthetic_values; "
    "generator=scripts/fixtures/finance_tcmb.py; "
    "source_document=scripts/fixtures/finance_tcmb_bulletin.xml; "
    "note=Kur degerleri TCMB'nin yayimladigi bir bultenden kopyalanmamistir; "
    "yalniz belge yapisi ve para birimi listesi canli sozlesmeden alinmistir."
)


class BulletinError(ValueError):
    """Bülten belgesi araç sözleşmesine çevrilemediğinde yükseltilir."""


@dataclass(frozen=True, slots=True)
class RateEntry:
    """Bültendeki tek bir para birimi satırı."""

    currency_code: str
    currency_name: str
    quotation_unit: int
    values: dict[str, float | None]

    def value_payload(self, rate_type: str) -> dict[str, Any] | None:
        """İstenen kur türü yayımlanmışsa araç çıktısındaki kur nesnesini verir."""

        value = self.values[rate_type]
        if value is None:
            return None
        return {
            "currency_code": self.currency_code,
            "currency_name": self.currency_name,
            "quotation_unit": self.quotation_unit,
            "value": value,
            "unit": "TRY",
        }


@dataclass(frozen=True, slots=True)
class Bulletin:
    """Bir yayım gününe ait normalize edilmiş kur bülteni."""

    bulletin_date: str
    entries: tuple[RateEntry, ...]

    def entry(self, currency_code: str) -> RateEntry | None:
        for entry in self.entries:
            if entry.currency_code == currency_code:
                return entry
        return None


def _optional_number(element: ElementTree.Element, field: str) -> float | None:
    """Boş bırakılmış alanı `None` yapar; TCMB efektif kurları böyle taşır."""

    text = (element.findtext(field) or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise BulletinError(f"{field} sayıya çevrilemedi: {text!r}") from exc


def parse_bulletin(xml_text: str) -> Bulletin:
    """TCMB `today.xml` belgesini bülten kaydına çevirir.

    Para birimleri belgedeki yayım sırasında korunur; `CrossOrder` sıralama için
    kullanılmaz çünkü TCMB belgeyi kendi yayım sırasıyla verir.
    """

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise BulletinError(f"bülten belgesi ayrıştırılamadı: {exc}") from exc

    day, month, year = (root.get("Tarih") or "").split(".")
    entries: list[RateEntry] = []
    for element in root.findall("Currency"):
        code = (element.get("CurrencyCode") or "").strip()
        name = (element.findtext("Isim") or "").strip()
        unit = (element.findtext("Unit") or "").strip()
        if not code or not name or not unit:
            raise BulletinError(f"eksik para birimi künyesi: {code or '?'}")
        entries.append(
            RateEntry(
                currency_code=code,
                currency_name=name,
                quotation_unit=int(unit),
                values={
                    rate_type: _optional_number(element, field)
                    for rate_type, field in RATE_TYPE_FIELDS.items()
                },
            )
        )
    if not entries:
        raise BulletinError("bültende hiç para birimi bulunamadı")
    return Bulletin(bulletin_date=f"{year}-{month}-{day}", entries=tuple(entries))


def build_rate_payload(
    bulletin: Bulletin,
    currency_code: str,
    rate_type: str,
    *,
    retrieved_at: str = RETRIEVED_AT,
) -> dict[str, Any]:
    """`finance_get_exchange_rate` çıktısını üretir.

    Yayımlanmamış kur bir hata değildir: kayıt beyan edilen biçimde döner ve
    `rate_available` alanı `false` olur.
    """

    if rate_type not in RATE_TYPE_FIELDS:
        raise BulletinError(f"bilinmeyen kur türü: {rate_type}")
    entry = bulletin.entry(currency_code)
    if entry is None:
        raise BulletinError(f"bültende bulunmayan para birimi: {currency_code}")
    rate = entry.value_payload(rate_type)
    return {
        "source": "TCMB",
        "retrieved_at": retrieved_at,
        "bulletin_date": bulletin.bulletin_date,
        "currency_code": currency_code,
        "rate_type": rate_type,
        "rate_available": rate is not None,
        "rate": rate,
    }


def build_list_payload(
    bulletin: Bulletin,
    rate_type: str,
    limit: int,
    *,
    retrieved_at: str = RETRIEVED_AT,
) -> dict[str, Any]:
    """`finance_list_exchange_rates` çıktısını üretir.

    İstenen türde kuru yayımlanmayan para birimleri listeye girmez; `count`
    döndürülen kayıt sayısıdır.
    """

    if rate_type not in RATE_TYPE_FIELDS:
        raise BulletinError(f"bilinmeyen kur türü: {rate_type}")
    if limit < 1:
        raise BulletinError(f"limit en az 1 olmalı: {limit}")
    rates = [
        payload
        for entry in bulletin.entries
        if (payload := entry.value_payload(rate_type)) is not None
    ][:limit]
    return {
        "source": "TCMB",
        "retrieved_at": retrieved_at,
        "bulletin_date": bulletin.bulletin_date,
        "rate_type": rate_type,
        "count": len(rates),
        "rates": rates,
    }


def build_fixtures(bulletin: Bulletin) -> dict[str, dict[str, Any]]:
    """Fixture kimliği -> fixture kaydı eşlemesini üretir."""

    specifications: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = [
        (
            "finance.tcmb.exchange_rate.usd_forex_selling.v1",
            "finance_get_exchange_rate",
            {"currency_code": "USD", "rate_type": "forex_selling"},
            build_rate_payload(bulletin, "USD", "forex_selling"),
        ),
        (
            "finance.tcmb.exchange_rate.ron_banknote_selling.v1",
            "finance_get_exchange_rate",
            {"currency_code": "RON", "rate_type": "banknote_selling"},
            build_rate_payload(bulletin, "RON", "banknote_selling"),
        ),
        (
            "finance.tcmb.exchange_rates.forex_selling_top5.v1",
            "finance_list_exchange_rates",
            {"rate_type": "forex_selling", "limit": 5},
            build_list_payload(bulletin, "forex_selling", 5),
        ),
    ]
    return {
        fixture_id: {
            "fixture_id": fixture_id,
            "function_name": function_name,
            "arguments": arguments,
            "result": result,
            "provenance": PROVENANCE,
        }
        for fixture_id, function_name, arguments, result in specifications
    }


def render(fixture: dict[str, Any]) -> str:
    """Depodaki fixture dosyalarıyla aynı biçimde metin üretir."""

    return json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bulletin",
        type=Path,
        default=BULLETIN_FILE,
        help="TCMB kur bülteni biçimindeki XML dosyası.",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=FIXTURE_DIR,
        help="Fixture dosyalarının yazılacağı dizin.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Dosyaları yaz; verilmezse çıktı yalnız ekrana basılır.",
    )
    arguments = parser.parse_args(argv)

    bulletin = parse_bulletin(arguments.bulletin.read_text(encoding="utf-8"))
    for fixture_id, fixture in build_fixtures(bulletin).items():
        text = render(fixture)
        if arguments.write:
            (arguments.fixture_dir / f"{fixture_id}.json").write_text(
                text,
                encoding="utf-8",
                newline="\n",
            )
            print(f"yazıldı: {fixture_id}.json")
        else:
            print(text, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover - komut satırı girişi
    raise SystemExit(main())
