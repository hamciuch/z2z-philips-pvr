# Sterowanie nagrywaniem (PVR) z Home Assistant — Philips 65PUS8857/12

TV: PH1M_EA_9970A, Android TV 11, RTT2.211108.001. Badanie z 2026-10-29, **tylko odczyt**:
`dumpsys package`, manifesty i DEX z pobranych APK (androguard), `content query`, `GET` na JointSPACE.
Nic nie zostało uruchomione, zaplanowane ani zmienione. Wszystko oznaczone „niesprawdzone” wynika z kodu,
nie z próby na TV.

## TL;DR

1. **Najlepsza droga dla HA: JointSPACE API 6.1 na porcie 1926** (serwuje je `org.droidtv.xtv`).
   `GET /6/system` deklaruje `jsonfeatures.recordings = ["List", "Schedule", "Manage"]` i
   `systemfeatures.content = ["dmr", "pvr"]`. Endpointy nagrań:
   `GET /6/recordings/list`, `POST /6/recordings/add`, `POST /6/recordings/conflictcheck`,
   `POST /6/recordings/groupaction`, `POST /6/recordings/refresh`, `GET /6/system/storage`.
   Wymagają digest auth (`pairing_type: digest_auth_pairing`) — tych samych poświadczeń, które ma już
   integracja Philips TV w HA. Bez nich: `HTTP 401` (sprawdzone).
2. **Lista nagrań i harmonogram są w providerze bez uprawnień**:
   `content://org.droidtv.playtv.provider.recordremind/RecordingsRemindersList.db/RecordingsTable`
   (82 wiersze na tym TV). Czytelny przez ADB `content query`.
3. **Klawisz `Record` istnieje w `/6/input/key`** (oraz `Play`, `Pause`, `Stop`, `Rewind`, `FastForward`,
   `TvGuide`) — nagrywanie bieżącego kanału jednym POST-em.
4. Intenty ADB do planowania (`org.droidtv.ACTION.SCHEDULE_*`) istnieją, ale to **aktywności z UI**
   (dialog na ekranie) — gorsza droga niż JointSPACE.

## 1. Pakiety

| Pakiet | Rola w PVR | uid |
|---|---|---|
| `org.droidtv.playtv` | odtwarzacz Live TV, sesje nagrywania (`RecService`, `PlayTvRecService`), alarmy, **provider nagrań** | system |
| `org.droidtv.channels` | EPG, UI listy nagrań (`epgui.RecordingsManager`), **dialogi planowania** | system |
| `org.droidtv.xtv` | **serwer JointSPACE** 1925/1926, `xtvRecordings.RecordingsManager` (REST → DB) | 10070 |
| `org.droidtv.xtvsystem` | backend dla xtv: zapisuje add/delete/update do providera playtv | system |
| `org.droidtv.epgdata` | Freeview Play / IP-EPG (UK), dla PL bez znaczenia | system |
| `/product/framework/tvfw.jar` | kontrakty (`IRecordingReminderContract`), enumy typów i błędów | — |

Log „`xtvsystem.xtvRecordings.RecordingsManager: sendRecordings:…`” widoczny co kilka sekund w logcat to
właśnie xtv/xtvsystem publikujące listę nagrań dla JointSPACE (`notifychange`).

## 2. Wystawione komponenty (exported, bez uprawnień, o ile nie zaznaczono)

### org.droidtv.playtv
| Typ | Komponent | Akcje / dane | Extras (z `onCreate`/`onReceive`) |
|---|---|---|---|
| activity | `.PlayTvActivity` | `MAIN`, `VIEW`, `org.droidtv.playtv.WATCH_TV`, `.SELECTURI`, mime `vnd.android.cursor.{dir,item}/{channel,program}` | — |
| activity | `.RecPlayActivity` | `org.droidtv.action.PLAYRECORDING`, `SEARCH` | `RecordingId` (int), `PVR_PLAYBACK_MODE_KEY` |
| activity | `.RecordDialogActivity` | `org.droidtv.action.RECORD_DIALOG` | `isSameChannel` (bool), `recId`, `channelId` (int), `est`, `eet` (long), `recordingType` (int), `recordingName` |
| activity | `.StopRecDialogActivity` | `org.droidtv.action.STOP_RECORD_DIALOG` | `recId` (int) |
| activity | `.ReminderActivity` | `org.droidtv.playtv.REMINDER` | — |
| service | `.recording.RecService`, `.services.PlayTvRecService` | (bez filtrów, exported) | — |
| service | `.services.StreamingService` | `org.droidtv.tunerservice.services.streamingservice.TVSTREAMINGCONTROL` / `…PLAYCONTROL` | — |
| receiver | `.bcastreceiver.AlarmReceiver` | `org.droidtv.playtv.PVRAlarmReceiver`, data scheme `rec` / `rem` | `reqId` (int) — wewnętrzny alarm startu nagrania |
| provider | `.provider.recordremind.RecordRemindProvider` | authority `org.droidtv.playtv.provider.recordremind`, **read/write permission: brak** | — |
| provider | `.search.ChannelSearchProvider` | `org.droidtv.tv.channels.search` | — |

### org.droidtv.channels
| Typ | Komponent | Akcja | Extras |
|---|---|---|---|
| activity | `epgui.ScheduleEventRecording` | `org.droidtv.ACTION.SCHEDULE_EVENT_RECORDING` | `channelid`, `eventid`, `eitversion`, `rectype`, `epgsource`, `serverrecordid`, `rating`, `EITSource`, `genre` (int); `starttime`, `duration` (long); `name`, `shortdescription` (String) |
| activity | `epgui.ScheduleRecording` | `org.droidtv.ACTION.SCHEDULE_RECORDING` | jak wyżej + `genreS`, `extendeddescription`, `repeatmode` (String), `episodecount` (long), `selectday`, `recordingid` (int) |
| activity | `epgui.ScheduleManualRecording` | `org.droidtv.ACTION.SCHEDULE_MANUAL_RECORDING` | `channelid` (int), `isipepg` (bool), `name`, `starttime`, `duration` (long), `serverrecordid` |
| activity | `epgui.ScheduleReminder` | `org.droidtv.ACTION.SET_REMINDER` | `channelid`, `eventid`, `starttime`, `endtime` (**int**), `name` |
| activity | `epgui.RecordingsManager` | `org.droidtv.ACTION.SHOW_RECORDINGS_LIST`, `org.droidtv.channels.GCDA_RECORDINGS` | `section`, `method_id` (int) |
| activity | `epgui.ManualRecordingActivity`, `epgui.UpdateRecordingActivity` | akcja = pełna nazwa klasy | — |
| activity | `ChannelsActivity` | `org.droidtv.action.GUIDE`, `org.droidtv.intent.action.SHOW_PLANNER`, `…CHANLIST` | — |
| activity | `epg.QsbIntentLauncher` | `VIEW`, scheme `tpvisiontvdvr` | — |
| receiver | `epg.bcepg.EpgBroadcastReceiver` | m.in. `org.droidtv.playtv.REC_START_NOTIFY`, `REC_END_NOTIFY` | — |
| provider | `epg.bcepg.EpgProvider` | authority `org.droidtv.epgdvb`, bez uprawnień | — |
| provider | `epg.search.EPGSearchProvider` | `org.droidtv.channels.epg.search` | — |
| service | `com.google.tv.contentsearch.ContentSearchService` | perm `com.google.tv.quicksearchbox.permission.DVR_SEARCH_SERVICE_ACCESS` | — |

Uwaga: wszystkie `Schedule*` to **aktywności** — `am start` pokaże dialog potwierdzenia na ekranie TV
(niesprawdzone, czy da się go pominąć). Jednostki `starttime`/`duration` w tych intentach: niesprawdzone
(w bazie są sekundy Unix, patrz niżej).

## 3. Providery — co da się przeczytać (sprawdzone `content query`)

### Nagrania i harmonogram
```
adb shell content query --uri content://org.droidtv.playtv.provider.recordremind/RecordingsRemindersList.db/RecordingsTable \
  --projection RecordingId:RecordingType:RecError:ChannelId:StartTime:Duration:EventName
```
Kolumny (46): `RecordingId RecordingType RecError IsIpEpgRec EventId ChannelId StartTime Duration MarginStart
MarginEnd EITVersion AutoMarginStart AutoMarginEnd EventInfo IsPartial RetentionInfo ResumeInfo RecName Size
HasLicenseFile ProgramNumber CICAMID LastPinChangedTime isFTARecording hasDot ServerRecordingId EventName
EventExtendedInfo EventGuidanceInfo EventGenre EventRating HasCicamPin EpisodeID SeriesID SeasonNo EpisodeNo
EpisodeCount Actual_Start_Time EITSource isRadio ProgramImageType AbsoluteTime ProgramDuration RealFilePath
RecGenreS Version`

- `StartTime` — sekundy Unix (UTC), `Duration` — sekundy.
- Zaplanowane nagrania to wiersze z `RecordingType=0` (SCHEDULED) / `11` (AUTO_PVR_SCHEDULED) — **jedna
  tabela na nagrania i harmonogram**. Na tym TV obecnie: 82 wiersze (48× NEW, 30× PARTIALLY_VIEWED,
  1× VIEWED, 3× FAILED), 0 zaplanowanych w przyszłości; błędy: 78× NONE, 3× NODISK, 1× CONFLICT.
- `RemindersTable` w tej samej bazie — teraz pusta. Inne nazwy tabel w kodzie: `RecordingTable`,
  `PirorityTable` (niesprawdzone, czy są wystawione).
- `content://android.media.tv/recorded_program` (TvContract) — **pusty**, Philips go nie używa.

Enumy (z `<clinit>` w `tvfw.jar`, `IRecordingReminderContract$IRecordingsContract`; wartości w bazie
zgadzają się z rozkładem powyżej):

| RecordingType | | RecError | |
|---|---|---|---|
| 0 SCHEDULED | 8 FAILED | 0 NONE | 7 EVENT_NOT_TRANSMITTED |
| 1 MANUAL | 9 USER_STOPPED | 1 DISKFULL | 8 NO_TRUSTED_CLOCK |
| 2 OTR (one-touch, klawisz Record) | 10 USER_DELETED | 2 CONFLICT | 9 TV_BUSY |
| 3 ONGOING | 11 AUTO_PVR_SCHEDULED | 3 NOPOWER | 10 NO_SIGNAL |
| 4 NEW | 12 AUTO_PVR_ONGOING | 4 POWERINTERRUPTION | 11 NO_CAM |
| 5 PARTIALLY_VIEWED | 13 AUTO_PVR_FAILED | 5 NODISK | 12 EPG_NOTACTIVE |
| 6 VIEWED | 14 AUTO_PVR_NEW | 6 IOERROR | 13 SYSTEM |
| 7 EXPIRED | 15 AUTO_PVR_EXPIRED | | |

### EPG (do wyboru audycji)
`content://org.droidtv.epgdvb/antenna/{nowtable,nexttable,indextable}` — bez uprawnień
(186 / 176 / 301 wierszy). `nowtable`: `eventid, presetid, eventname, starttime, endtime` (sekundy Unix),
`shortinfo, genre, rating…`; `indextable`: `presetid, presetnumber, channelname, sid, tsid, onid…`.
Pełny harmonogram (poza now/next) — w kodzie jest `antenna/scheduletablesync`, nie odpytywane
(nazwa sugeruje operację, nie odczyt).

**Niewyjaśnione:** przestrzeń `ChannelId` w `RecordingsTable` (np. 2442) ≠ `_id` w TvContract
(`android.media.tv/channel/2442` → brak) i ≠ `presetid` z EPG (3001, 3004…). xtvsystem mapuje JointSPACE
`ccid` → `ChannelId`, więc najpewniej to `ccid` z `GET /6/channeldb/tv/channelLists/all` — do potwierdzenia
po uwierzytelnieniu.

## 4. JointSPACE — nagrania (z kodu xtv/xtvsystem; GET /6/system sprawdzony)

Trasy zarejestrowane w `xtvRequestHandler.createInboundRoot` (prefiks `/6/`):
`/recordings/list`, `/recordings/add`, `/recordings/conflictcheck`, `/recordings/groupaction`,
`/recordings/refresh`, `/system/storage`, `/channeldb/tv`, `/channeldb/tv/channelLists/{id}`,
`/activities/tv`, `/input/key`, `/notifychange`, `/powerstate`, `/context`, ambilight…

**Pola obiektu nagrania** (`RecordingsManager.readDataObject` w xtv → `getContentValues` w xtvsystem):
`RecordingType, IsIpEpgRec, ccid, StartTime, Duration, MarginStart, MarginEnd, EventId, EventInfo,
EventExtendedInfo, EventGenre, RecName, EventName, EpisodeID, SeriesID, SeasonNo, EpisodeNo, EpisodeCount,
ProgramNumber, Medium, RecordingId`. `ccid` zapisywane jest jako `ChannelId`.

**`groupaction`**: `{"actions":[{"action":"add|update|delete","data":{…pola jak wyżej…}}]}` — xtvsystem
robi z tego `applyBatch` na providerze playtv (`delete`/`update` po `RecordingId = ?`).

**`conflictcheck`** zwraca obiekty z `RecordingId, ResolveAction` (`resolve_action_delete` /
`resolve_action_partial_recording`), `ResolveActionGroup, EffectivStartTime, EffectiveEndTime, RecName`.

**`list`** zwraca m.in. `RecordingId, RecordingType, StartTime, Duration, MarginStart, MarginEnd, EventId,
EITVersion, RetentionInfo, ServerRecordingId, IsPartial, IsIpEpgRec, …` plus `version`; zmiany
ogłaszane przez `/6/notifychange` jako `recordings/list` z nowym `version`.

Niesprawdzone: czy `RecordingType` w JSON jest liczbą czy nazwą enum (jest `getRecTypeString`), czy
`StartTime` to sekundy, i czy `add` bez wcześniejszego `conflictcheck` zostaje przyjęty.

Szkic do HA (`rest_command`, digest auth jak integracja; **niesprawdzony**):
```yaml
rest_command:
  philips_record_event:
    url: "https://<tv ip>:1926/6/recordings/add"
    method: POST
    verify_ssl: false
    authentication: digest
    username: !secret philips_user      # z pary utworzonej przez integrację Philips TV
    password: !secret philips_pass
    content_type: "application/json"
    payload: >
      {"RecordingType":0,"ccid":{{ ccid }},"EventId":{{ event_id }},
       "StartTime":{{ start }},"Duration":{{ duration }},"MarginStart":0,"MarginEnd":0,
       "RecName":"{{ name }}","EventName":"{{ name }}","IsIpEpgRec":false}
```
Lista do sensora: `rest` z `GET /6/recordings/list` (ten sam auth).

## 5. Klawisze `/6/input/key`

`POST /6/input/key` z `{"key":"<Nazwa>"}`. TV deklaruje `jsonfeatures.inputkey = ["key"]` (bez listy);
nazwy z tabeli w `xtv`:

- **Nagrywanie i odtwarzanie:** `Record`, `Play`, `Pause`, `Stop`, `Rewind`, `FastForward`, `TvGuide`
- Nawigacja: `CursorUp/Down/Left/Right`, `Confirm`, `Back`, `Home`, `Options`, `Find`, `Adjust`, `Online`
- Kanały i źródła: `ChannelStepUp/Down`, `Digit0–9`, `Dot`, `WatchTV`, `Source`, `Teletext`, `Subtitle`,
  `Viewmode`
- Kolory: `GreenColour`, `YellowColour`, `BlueColour` (`RedColour` nie wyszedł w wyszukiwaniu ciągów —
  standardowo istnieje w JointSPACE, niesprawdzone)
- Inne: `Standby`, `VolumeUp/Down`, `Mute`, `AmbilightOnOff`

`Record` na Live TV = nagranie natychmiastowe (typ OTR = 2), najpewniej przez `RecordDialogActivity`
(dialog z czasem końca) — niesprawdzone. `Stop` w trakcie nagrania → `StopRecDialogActivity`.

## 6. Droga przez ADB (rezerwowa, niesprawdzona)

```sh
# lista nagrań / harmonogramu (sprawdzone, tylko odczyt)
content query --uri content://org.droidtv.playtv.provider.recordremind/RecordingsRemindersList.db/RecordingsTable
# otwarcie listy nagrań na ekranie
am start -a org.droidtv.ACTION.SHOW_RECORDINGS_LIST
# dialog zaplanowania audycji z EPG (pokaże UI na TV)
am start -a org.droidtv.ACTION.SCHEDULE_EVENT_RECORDING --ei channelid <id> --ei eventid <eventid> \
  --el starttime <unix s> --el duration <s> --es name "<tytuł>" --ei rectype 0
```
Provider nie ma `writePermission`, więc `content insert` też by przeszedł — **odradzane**: omija
xtvsystem i playtv (alarmy `PVRAlarmReceiver` nie zostaną ustawione), nagranie najpewniej nie wystartuje.
ADB zostanie też zamknięte na koniec debloatu, więc dla HA właściwa droga to JointSPACE.

## 7. Kolejne kroki (każdy zmienia stan TV — tylko za zgodą)

1. Z poświadczeniami HA: `GET /6/recordings/list` i `GET /6/channeldb/tv/channelLists/all` — potwierdzić
   format i przestrzeń `ccid`.
2. `POST /6/recordings/conflictcheck` z jednym testowym obiektem (nie zapisuje — do sprawdzenia).
3. Jedno testowe `recordings/add` na krótką audycję, sprawdzenie w `RecordingsTable` i w UI, potem
   `groupaction` `delete`.

## 8. Wyniki testów z poświadczeniami (2026-10-29, 13:28–13:50)

Poświadczenia z `~/.philips-tv.env` (`PHILIPS_USER`, `PHILIPS_PASS`), przekazywane do `curl --digest -K -`
przez stdin; nigdzie nie zapisane w repo. Odpowiedzi API trzymane w scratchpadzie, nie w `work/`.

### Rozstrzygnięte

**`ccid` = `ChannelId` = EPG `presetid`.** Jedna przestrzeń ID:
- `RecordingsTable.ChannelId` == `ccid` z `/6/recordings/list` dla 82/82 nagrań,
- `presetid` z `epgdvb/antenna/nowtable` należy do zbioru `ccid` z `/6/channeldb/tv/channelLists/all` dla 185/185,
- `/6/activities/tv` zwraca bieżący kanał też jako `ccid` (`{"channel":{"ccid":2993,"preset":"27","name":"TVP INFO HD"}}`).
- Stare `ChannelId` (np. 2442) to kanały spoza obecnej listy (tylko 2/82 starych nagrań ma kanał na obecnej
  liście) — najpewniej sprzed przestrojenia. Odtwarzanie ich nie było testowane.
- `channelLists/all`: 284 kanały (223 DVB-C, 61 analog; 273 TV, 11 radio). Pola: `ccid, preset, name, sid,
  tsid, onid, serviceType, type, logoVersion`.
- `epgdvb` ignoruje `--projection` w `content query` (zwraca wszystkie kolumny).

**`RecordingType` i `RecError` w JSON to nazwy enum jako String** (`"RECORDING_SCHEDULED"`,
`"RECORDING_NEW"`, `"REC_ERROR_NO_CAM"`), w providerze — liczby (tabela w sekcji 3). Parser
`readDataObject` czyta: `RecordingType` String, `IsIpEpgRec` bool, `ccid` int, `StartTime` long (sekundy Unix),
`Duration`/`MarginStart`/`MarginEnd` int (sekundy), `EventId` **String** (w odpowiedzi `list` wraca jako int),
`EventGenre`/`RecName`/`EventName`/`EventInfo` String, `SeasonNo`/`EpisodeNo` int.
`list` zwraca też: `RecError`, `isFTARecording`, `HasCicamPin`, `HasLicenseFile`, `Size`, `ActualStartTime`,
`ProgramNumber`, `EITSource`, `IsRadio`, `Version`.

### Zachowanie endpointów (sprawdzone)

| Wywołanie | Odpowiedź | Efekt |
|---|---|---|
| `GET /6/recordings/list` | `200 {"version":"610.291","recordings":[…]}` | `version` rośnie przy każdej zmianie |
| `POST /6/recordings/conflictcheck` | `200 {}` gdy brak konfliktów | **nic nie zapisuje** (liczba wierszy bez zmian) |
| `POST /6/recordings/add` | `200 {"Error":"rec_error_none","RecordingId":119}` | wiersz w providerze + alarm `playtv` `PVRAlarmReceiver` (event: 20 min przed startem; manual: 1 min przed) |
| `POST /6/recordings/groupaction` `{"actions":[{"action":"delete","data":{"RecordingId":N}}]}` | **`503 Service Unavailable`** (HTML) — 2/2 razy | **wiersz mimo to usunięty** z providera i z `list` |
| `GET /6/system/storage` | `{"status":"Mounted","totalcapacity":238384,"recordingstotal":238384,"recordingsusage":63202}` (MB) | — |

Wniosek dla HA: po `groupaction` nie ufać kodowi HTTP — po każdej zmianie odczytać `recordings/list`.
`groupaction` `update` nie był testowany.

Body użyte do `add` (event z EPG):
```json
{"RecordingType":"RECORDING_SCHEDULED","IsIpEpgRec":false,"ccid":3181,"StartTime":1793278800,
 "Duration":120,"MarginStart":0,"MarginEnd":0,"EventId":"21459","RecName":"DW News",
 "EventName":"DW News","EventInfo":"…","EventExtendedInfo":"","EventGenre":"0"}
```
Nagranie ręczne (po czasie, bez audycji): `"RecordingType":"RECORDING_MANUAL"`, `"EventId":""` → w providerze
`RecordingType=1`, w `list` `EventId: 0`. Dla nagrania zmienionego w czasie użyć MANUAL: nagranie event-based
jest związane z `EventId` i może się przesuwać za audycją w EIT (niesprawdzone).

### Przebieg testu

1. `add` event DW News (ccid 3181, 14:00, 120 s) → `RecordingId 119`, `RECORDING_SCHEDULED`, alarm 13:40.
2. Na prośbę właściciela zmiana na 13:40–13:45: `delete` 119 (503, ale usunięte) + `add` MANUAL
   (13:40, 300 s) → `RecordingId 120`, alarm 13:39.
3. 13:40 — nagranie wystartowało (`ActualStartTime` = 13:40:00, plik `/pvr/CH808/1029_134002.pvr`), TV
   pozostał na `PlayTvActivity` (oglądany TVP INFO HD) — nagrywanie w tle.
4. 13:41 — **`RECORDING_FAILED`, `REC_ERROR_NO_CAM` (11)**, `Size 0`, `isFTARecording: false`.
5. 13:47 — `delete` 120 (503, ale usunięte). Stan końcowy: 82 wiersze, jak przed testem.

**Ścieżka API działa w całości** (add → alarm → start nagrania → status w `list` → delete).
**Samo nagranie się nie udało: `NO_CAM`.** W TV jest karta CI (moduł CAM/CI+). TV oznaczył kanał DW jako
nie-FTA (`isFTARecording: false`), czyli wymagający deszyfrowania. Przyczyny nie dało się ustalić z logu
(`playtv` loguje tylko alarm i start usługi, reszta wycięta przez `chatty`). Hipotezy, niesprawdzone:
- moduł CAM deszyfruje tylko jeden kanał naraz i był zajęty oglądanym TVP INFO HD, więc drugi tuner nie
  dostał deszyfrowania — najczęstsze ograniczenie;
- DW nie jest w pakiecie karty;
- CI+ operatora blokuje nagrywanie (wtedy błąd byłby raczej `CAM_FAILED` niż `NO_CAM`).

Następny test, który to rozstrzyga (za zgodą): nagranie MANUAL **tego samego kanału, który jest oglądany**
(CAM już go deszyfruje), albo nagranie w czasie, gdy TV jest w standby.

### Format nagrań i Jellyfin

- Pliki `.pvr` platformy MediaTek, np. `/pvr/CH808/1029_134002.pvr`, na dysku USB 238 GB
  sformatowanym przez TV. Punkt montowania `/pvr` jest prywatny dla systemu — shell ADB go nie widzi
  (`No such file or directory`), więc nagłówka pliku nie sprawdzono.
- Wg instrukcji Philips dysk jest formatowany na wyłączność dla tego TV, a nagrań nie da się odtworzyć na
  innym urządzeniu (szyfrowanie powiązane z TV; dla kanałów z CI+ dodatkowo prawa operatora — kolumny
  `HasLicenseFile`, `HasCicamPin`, `CICAMID`). JointSPACE nie ma endpointu do pobrania pliku.
- **Jellyfin: nie.** Nagrania do Jellyfin musi robić serwer (tuner sieciowy DVB-C + Jellyfin Live TV/DVR
  lub Tvheadend). Tuner bez CI nagra tylko kanały niekodowane.

### Kodowanie kanałów (niezweryfikowane)

Flaga `scrambled` w `epgdvb` now/next = 0 dla wszystkich 186 kanałów, również dla HBO/Canal+/Eleven/Polsat
Sport — **operator jej nie ustawia, jest bezużyteczna**. Lista kanałów JointSPACE i `indextable` nie mają
pola o kodowaniu; TvContract jest dla shella pusty. Jedyny sygnał z TV: `isFTARecording` w nagraniu
(DW → `false`). Pewne rozstrzygnięcie: lista FTA od operatora albo skan tunerem sieciowym bez karty.

### Do HA — podsumowanie

- Lista/harmonogram: `rest` sensor na `GET /6/recordings/list` (digest), filtr po `RecordingType`.
- Zaplanowanie z EPG: `conflictcheck` → `add` (body jak wyżej, `EventId` jako String, `ccid` z
  `channelLists/all` albo z EPG `presetid`).
- Anulowanie: `groupaction` `delete` → zignorować 503 → potwierdzić przez `list`.
- Szybkie nagrywanie bieżącego kanału: `POST /6/input/key {"key":"Record"}` (niesprawdzone).
- Zajętość dysku: `GET /6/system/storage`.

## 9. Testy A/B: CAM, standby i kanały istniejących nagrań (2026-10-29, 13:51–14:17)

### Kanały 82 istniejących nagrań (ChannelId → nazwa)
`ccid` spoza obecnej listy dopasowane po `ProgramNumber` = `sid` z `channelLists/all` (wszystkie jednoznacznie):

| Kanał | Nagrań | Wynik | Wymaga CAM? |
|---|---|---|---|
| 310 AXN Black | 76 | 74 OK, 2× NODISK | tak (płatny) |
| 5 TVN HD | 1 | OK | nieznane |
| 50 TVN Turbo HD | 2 | OK | nieznane |
| 22 TVN24 BiS HD | 1 | OK | nieznane |
| 23 Polsat News HD | 1 | OK | nieznane |
| 214 TVP Sport HD | 1 | NODISK | nieznane |

`isFTARecording=false`, `HasCicamPin=false`, `CICAMID` puste w **wszystkich** nagraniach, także w udanych z
AXN Black przez kartę CI — **te pola nie mówią nic o kodowaniu ani o udziale CAM**. Nagrywanie przez CAM na
tym TV działa (74 udane nagrania AXN Black).

### Test A — kanał aktualnie oglądany (DW, ccid 3181), ekran włączony
MANUAL 13:53, 120 s → `RecordingId 121` → `RECORDING_NEW`, `REC_ERROR_NONE`, `Duration 119`,
plik `/pvr/CH808/1029_135301.pvr`. **Udane.** Wniosek: `NO_CAM` z 13:40 (sekcja 8) wynikał najpewniej z tego,
że CAM deszyfrował inny, oglądany kanał (TVP INFO HD) — moduł obsługuje jeden kanał naraz.

### Test B — DW w standby
MANUAL 14:00, 120 s → `RecordingId 122`. TV w standby od 13:55:52 (`power_sleep_requested`).
- Start 13:59:30 (`Actual_Start_Time`, 30 s przed czasem), `RecService` jako foreground service
  z powiadomieniem `RecOn_ChannelID`, `PARTIAL_WAKE_LOCK 'RecService'`, CAM bez błędu.
- **Nie zatrzymało się po 120 s.** O 14:11 provider i `/6/recordings/list` zgodnie: `ONGOING`
  (to nie nieodświeżony stan API). `RecService`/`MtkTvInput` co sekundę `notifyRecordNotification type=7`.
- Zakończyło się samo o **14:12:02** (zwolnienie wakelocka), **przed** wybudzeniem TV (ekran 14:13:52).
  W providerze: `RecordingType=4` (NEW), `RecError=0`, **`Duration=720`** zamiast 120.
- Przyczyna 12 min nieznana (zbieżność z `TIME_TICK`/alarmem `channels START_BG_MUXITRATION` o 14:12:00
  niepotwierdzona). Do sprawdzenia, czy w standby zawsze nagrywa dłużej (np. minimum 12 min).

### Inne obserwacje API
- `groupaction` `delete` — 4/4 wywołania (także dwa usunięcia w jednym `actions[]`) zwróciły **503**, wszystkie
  skuteczne.
- `GET /6/recordings/list` czasem zwraca **200 z pustym body** (4 razy w ciągu 20 min, także zaraz po zmianie
  stanu) — w kodzie xtv jest ścieżka „list not modified”. HA: pusty 200 traktować jak „brak danych”, ponowić.
- JointSPACE (1926) i ADB odpowiadają w standby.

### Wnioski dla HA (uzupełnienie sekcji 8)
- Planować nagrania na kanale, który nie wymaga CAM, albo gdy TV jest w standby / na tym samym kanale —
  inaczej możliwe `REC_ERROR_NO_CAM`.
- W standby liczyć się z dłuższym nagraniem niż `Duration` (test B: 12 min zamiast 2).
- Sensor: alarm, gdy `ONGOING` trwa dłużej niż `StartTime + Duration + MarginEnd`; błąd z pola `RecError`.

Stan końcowy: 82 nagrania, jak przed testami (119–122 usunięte).
