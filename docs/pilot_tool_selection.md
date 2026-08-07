# Pilot tool selection dossier

Status: research candidates only. No entry in this document is approved for
production or live dataset generation. Terms were last checked on 2026-08-07.

## Decision rules

A tool can move from `candidate` to `approved` only when its input and output
schemas, execution mode, reproducible fixture, source provenance, license or
permission basis, freshness rule, and do-not-use boundary have all been
reviewed. Live sources are never called while evaluating a frozen dataset
record. Live access is used only for contract checks and fixture refreshes.

Provider names belong in access/provenance metadata. Function names remain
provider-neutral unless the provider defines unique semantics that cannot be
represented generically.

## General Turkish candidates

| Tool ID / function | Contract summary | Execution and fixture plan | Evidence, risk, and boundary |
|---|---|---|---|
| `calculator.evaluate.v1` / `calculator_evaluate` | Required `expression`; returns numeric `result` and normalized expression. Example: “18'in yüzde 25'ini hesapla.” | `local_executable`; curated arithmetic fixtures plus property tests. | Static, no auth, no PII. Permit only a small arithmetic grammar; never use `eval`, code execution, financial advice, or symbolic algebra claims. |
| `calculator.convert_units.v1` / `calculator_convert_units` | Required `value`, `from_unit`, `to_unit`; returns converted value and units. Example: “90 kilometre/saat kaç metre/saniye?” | `local_executable`; versioned conversion table and boundary fixtures. | Static, no auth, no PII. Reject incompatible dimensions and unsupported currency conversion. |
| `time.convert_timezone.v1` / `time_convert_timezone` | Required local timestamp, source zone, target zone; returns ISO timestamp, offsets, and ambiguity warning. | `local_executable`; Python zoneinfo with the runtime tzdata identity recorded. | Time-sensitive rules. Reject unknown zones; surface DST ambiguity instead of guessing. |
| `weather.get_forecast.v1` / `weather_get_forecast` | Required location and forecast date; optional unit; returns dated daily forecast with source time. | `mock` for dataset, contract-checked `real_api` candidate. Immutable fixtures keyed by place/date/retrieval time. | Open-Meteo weather API and attribution terms: https://open-meteo.com/en/docs and https://open-meteo.com/en/terms. Volatile; not an emergency warning service. |
| `air_quality.get_current.v1` / `air_quality_get_current` | Required coordinates or resolved place; returns timestamped pollutant values and index metadata. | `mock` for dataset, contract-checked `real_api` candidate. | Open-Meteo Air Quality API: https://open-meteo.com/en/docs/air-quality-api. Volatile; never provide medical diagnosis or safety guarantees. |
| `geo.search_places.v1` / `geo_search_places` | Required query; optional country and result limit; returns stable local IDs, display names, coordinates, and administrative hierarchy. | Pilot default is `mock`. Promote to `local_executable` only after a frozen Türkiye OSM extract and deterministic ranking implementation are checked in. | ODbL attribution: https://www.openstreetmap.org/copyright. Public Nominatim is not used for bulk generation: https://operations.osmfoundation.org/policies/nominatim/. Do not claim official NVI/UAVT validation. |
| `route.plan.v1` / `route_plan` | Required origin, destination, and travel mode; returns distance, duration, and ordered route summary. | Pilot default is `mock`. Promote to `local_executable` only after a frozen OSM/OSRM graph, checksum, and reproducible runner exist. | OSM/OSRM provenance. Estimates only; no emergency routing, live traffic, or road-safety guarantee. |
| `knowledge.search.v1` / `knowledge_search` | Required query; optional language and limit; returns titles, summaries, canonical URLs, and source IDs. The pilot fixture pins a Turkish Wikipedia revision rather than a mutable or placeholder URL. | `mock` for dataset, read-only API candidate with frozen responses. | Wikimedia search API: https://www.mediawiki.org/wiki/API:Search/en. Preserve the pinned source URL, CC BY-SA 4.0 attribution, and share-alike chain; no unsupported factual synthesis. |
| `calendar.list_events.v1` / `calendar_list_events` | Required date range; optional calendar and query; returns synthetic events with stable IDs. | Resettable `fully_simulated` state; seeded calendars and deterministic clock. | Synthetic data only. Never connect to a real account or include real names, addresses, or meeting links. |
| `calendar.create_event.v1` / `calendar_create_event` | Required title/start/end; optional location and notes; returns synthetic event ID and state. | Resettable `fully_simulated`; explicit before/after fixture. | Stateful and confirmation-sensitive. The scenario must require confirmation when important details are inferred; no external invitations or real calendar writes. |

## Türkiye-native candidates

| Tool ID / function | Contract summary | Execution and fixture plan | Evidence, risk, and boundary |
|---|---|---|---|
| `holiday.is_business_day.v1` / `holiday_is_business_day` | Required Turkish date; returns business day, weekend, full holiday, or half-day holiday status and reason. | `local_executable`; versioned annual table derived from current law and official calendars. Unsupported years fail instead of being guessed. | 2429 law record: https://www5.tbmm.gov.tr/tutanaklar/KANUNLAR_KARARLAR/kanuntbmmc064/kanunmgkc064/kanunmgkc06402429.pdf. Does not model employer-specific leave or bank cut-off rules. |
| `earthquake.search_events.v1` / `earthquake_search_events` | Required time range; optional magnitude and bounding box; returns event ID, time, magnitude, depth, and coordinates. | Immutable `mock` by default; `real_api` remains blocked until redistribution/terms are documented. | AFAD event service: https://deprem.afad.gov.tr/event-service. Historical observation only; no prediction, safety instruction, or casualty inference. |
| `ev.search_chargers.v1` / `ev_search_chargers` | Required location/radius; optional connector, minimum power, and availability; returns station/operator/connector/price metadata with observation time. | `mock` first; read-only `real_api` candidate after exact Swagger contract and reuse terms are approved. | EPDK services: https://www.epdk.gov.tr/Detay/Icerik/3-0-226/web-servisler. Availability and prices are volatile; no reservation or charging-session action. |
| `fuel.get_prices_by_province.v1` / `fuel_get_prices_by_province` | Required province code; optional product; returns timestamped price observations and unit. | `mock` first. Current source is XML and needs a separately reviewed adapter before live use. | EPDK fuel service: https://www.epdk.gov.tr/Detay/Icerik/3-0-158/akaryak. No price guarantee or station-level claim unless the source supplies it. |
| `school_calendar.get.v1` / `school_calendar_get` | Required academic year; optional typed event filter. `all_breaks` returns both `interim_break` and `semester_break`; term and report-card events remain separate. Results carry a source version. | Pilot default is `mock`. Promote to `local_executable` only after the official annual record is stored as validated, versioned local data with a lookup implementation. | MEB calendar source: https://meb.gov.tr/2026-2027-egitim-ogretim-yili-takvimi-aciklandi/haber/41057/tr. Do not collapse ara tatil and yarıyıl tatili into one semantic type; surface regional exceptions and do not infer a specific school's closure. |
| `exam_calendar.search.v1` / `exam_calendar_search` | Required exam query and optional year; returns application dates, every named exam session, and result date when published. | Pilot default is `mock`. Promote to `local_executable` only after a versioned local snapshot and query implementation exist. | ÖSYM calendar: https://www.osym.gov.tr/. Dates may change; no candidate result, application, payment, or account access. |
| `prayer.get_times.v1` / `prayer_get_times` | Required official location ID and date; returns named prayer times and timezone. | `mock` until institutional credentials, quota policy, and reuse permission are approved; later contract-checked `real_api`. | Diyanet service and guide: https://awqatsalah.diyanet.gov.tr/index.html. JWT secrets never enter logs/fixtures; location ambiguity must be resolved explicitly. |
| `pharmacy.find_on_duty.v1` / `pharmacy_find_on_duty` | Required province, district, and date (`today` or `tomorrow`); returns pharmacy name, public address, phone, and duty interval. | Immutable `mock`; no scraping. Refresh only through an approved official interface. | Official TİTCK service UI: https://www.turkiye.gov.tr/saglik-titck-nobetci-eczane-sorgulama. Highly time-sensitive; not medical advice and never claim availability beyond the source timestamp. |
| `parcel.get_status.v1` / `parcel_get_status` | Required synthetic tracking ID; returns normalized status, event time, and coarse location. | `mock` in pilot; authenticated partner/sandbox candidate later. All identifiers are synthetic. | MNG developer portal: https://apizone.mngkargo.com.tr/en/node/3973. No real customer name, address, phone, shipment creation, rerouting, or cancellation. |
| `research.search_publications.v1` / `research_search_publications` | Required query; optional year, author, and limit; returns title, authors, year, DOI/record ID, source, and record license. | `mock` first; read-only source adapters considered separately after reuse terms are approved. | TR Dizin API documentation: https://development.trdizin.gov.tr/ and Aperta: https://ulakbim.tubitak.gov.tr/turkiye-acik-arsivi-aperta/. Preserve per-record license; do not invent DOI or access rights. |

## Approval blockers and replacements

The following candidates cannot enter the approved registry until the blocker is
resolved:

- AFAD: explicit reuse/redistribution basis for public fixtures.
- EPDK charging: exact current Swagger request/response contract and reuse terms.
- EPDK fuel: XML adapter decision and fixture provenance.
- Diyanet: institutional access, quota ownership, and reuse permission.
- Duty pharmacy: a documented external interface; scraping is not acceptable.
- Parcel tracking: sandbox/partner access and synthetic identifier policy.
- Research search: provider-specific license handling.

If a blocker remains at blueprint freeze time, the tool may stay in the pilot
only as `mock` or `fully_simulated` with fully synthetic data. It must not claim
that a real provider call was executed. A blocked native tool can be replaced by
`statistics.get_series`, `culture.list_events`, or `transit.plan_journey` after
the same proposal review.

## Proposed pilot balance

- 4 deterministic local tools with implemented adapters
- 2 resettable fully simulated calendar tools
- 14 immutable mock tools, including every source with unresolved access,
  licensing, snapshot, or live-contract work

All 20 candidate fixtures pass schema validation. Representative CLI execution
has passed in all three active modes. Candidate lifecycle remains unchanged;
blueprint authoring may proceed against the proposal registry, but live dataset
generation requires a separate approval decision and canonical-registry
promotion.

This balance is evaluated at blueprint freeze. Tool count is capped at 20 for
the 30-record technical pilot; expanding the domain catalog does not expand the
active tool set automatically.
