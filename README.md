# Z2Z Philips PVR

Integracja Home Assistant do **planowania i obsługi nagrań** na telewizorach Philips z Android TV
(nagrywanie na dysk USB podłączony do TV), przez lokalne API **JointSPACE** (port 1926, digest auth).

Sprawdzone na **Philips 65PUS8857/12** (Android TV 11). Szczegóły API, testy i znane dziwactwa:
[docs/recording-research.md](docs/recording-research.md).

## Co daje

| Encja | Opis |
|---|---|
| `sensor.*_recordings` | liczba nagrań; atrybut `recordings` = 20 najnowszych (id, nazwa, kanał, start, status, błąd) |
| `sensor.*_scheduled_recordings` | liczba zaplanowanych; atrybut `scheduled` |
| `sensor.*_next_recording` | start najbliższego nagrania (timestamp) + szczegóły w atrybutach |
| `sensor.*_disk_free` / `*_disk_used` | wolne miejsce (GB) / zajętość (%) dysku nagrań |
| `binary_sensor.*_recording` | trwa nagrywanie |
| `binary_sensor.*_recording_failed` | nieudane nagranie w ostatnich 2 dniach (np. `REC_ERROR_NO_CAM`, `NODISK`) |
| `binary_sensor.*_recording_disk` | problem z dyskiem (nie `Mounted`) |
| `binary_sensor.*_recording_overrun` | nagranie trwa >15 min dłużej niż planowano |
| `calendar.*_recordings` | kalendarz nagrań (tylko odczyt) |

### Usługi

```yaml
# Nagraj film: kanał jak na pilocie (albo nazwa / ccid), start + koniec lub czas trwania
action: z2z_philips_pvr.record
data:
  channel: "310"          # albo "AXN Black"
  start: "2026-10-30 21:55:00"
  end: "2026-10-30 23:50:00"
  name: "Film wieczorny"
response_variable: wynik   # {recording_id, channel, start, end, confirmed, warnings}

# Nagrywaj teraz (start w ciągu ~2 min) — domyślnie oglądany kanał
action: z2z_philips_pvr.record_now
data:
  duration: "01:30:00"

# Anuluj zaplanowane / usuń nagranie (UWAGA: gotowe nagranie znika z dysku TV)
action: z2z_philips_pvr.delete_recording
data:
  recording_id: 119
```

Start w przeszłości (program już leci) → nagrywa resztę programu.
`force: true` planuje mimo konfliktu zgłoszonego przez TV.

## Instalacja

1. HACS → Custom repositories → `https://github.com/hamciuch/z2z-philips-pvr` (Integration) → zainstaluj → restart HA.
2. Ustawienia → Urządzenia i usługi → Dodaj → **Z2Z Philips PVR**.
3. Jeśli masz już integrację **Philips TV** — wybierz „Użyj danych logowania z integracji Philips TV”.
   Inaczej podaj IP i dane digest JointSPACE ręcznie.

## Ważne ograniczenia (z testów na żywym TV)

- **Karta CI / CAM deszyfruje jeden kanał naraz.** Nagranie kodowanego kanału, gdy TV jest włączony
  i pokazuje *inny* kanał, kończy się `REC_ERROR_NO_CAM`. W standby albo na tym samym kanale działa.
  Usługi zwracają ostrzeżenie w `warnings`, gdy TV jest włączony na innym kanale.
- **W standby TV potrafi nagrywać dłużej** niż zaplanowano (test: 12 min zamiast 2).
- **Nagrania są szyfrowane i powiązane z TV** — nie da się ich skopiować ani odtworzyć w Jellyfin.
- API ma dziwactwa, które integracja obsługuje: `recordings/list` czasem zwraca pusty `200`
  (zostaje poprzedni stan), `groupaction delete` zwraca `503` mimo sukcesu (wynik sprawdzany na liście).
- Nagrania planowane są „po czasie” (`RECORDING_MANUAL`). Planowanie po audycji z EPG wymaga EPG,
  którego JointSPACE nie udostępnia.

## Test na żywo (bez Home Assistant)

```bash
pip install httpx
python3 scripts/smoke_test.py 192.168.23.100           # tylko odczyt
python3 scripts/smoke_test.py 192.168.23.100 --write   # + dodaj i usuń testowe nagranie (jutro 03:00, 1 min)
```

Dane logowania z `~/.philips-tv.env` (`PHILIPS_USER=…`, `PHILIPS_PASS=…`) — nie są nigdzie wypisywane.

## Rozwój

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest -q -p no:logging
```
