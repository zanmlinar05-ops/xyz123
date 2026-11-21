# Moj Urnik – podatkovna baza in FRI scraper

Dokumentacija podatkovnega dela projekta **Moj Urnik** (UL FRI). Ta del backenda pridobiva podatke z uradnega portala FRI urnik, jih hrani v PostgreSQL, uvaža študentove uradne dodelitve in omogoča branje urnika za nadaljnjo uporabo v FastAPI in React aplikaciji.

> **Obseg dokumentacije:** opis temelji na izhodiščnih datotekah projekta in funkcionalnostih, ki smo jih naknadno skupaj implementirali ter lokalno preizkusili (`app/sync.py`, `app/schedule.py`, `test_real_student.py`, `test_schedule.py`). Ker se je del kode urejal neposredno na lokalnem računalniku, je treba pred oddajo preveriti, da se imena funkcij in njihovi podpisi ujemajo s končno lokalno različico.

## 1. Funkcionalnosti

- **Globalni scraper:** pridobivanje seznama predmetov, terminov, skupin, izvajalcev, učilnic, kapacitet in zasedenosti s portala FRI.
- **Podatkovna baza:** PostgreSQL s podatkovnim modelom SQLAlchemy in migracijami Alembic.
- **Ponovljiv uvoz:** ob ponovnem uvozu se obstoječi podatki posodobijo, novi dodajo; zapisi se ne podvajajo na podlagi FRI identifikatorjev in omejitev unikatnosti.
- **Študentski scraper:** pridobivanje uradnih terminov za vpisno številko in shranjevanje povezav med študentom in termini.
- **Sinhronizacija:** preverjanje zadnjega uspešnega uvoza ter dnevno osveževanje globalnih podatkov.
- **Aktualni semester:** določitev aktualnega semestra iz končnega URL-ja FRI portala po HTTP preusmeritvi.
- **Branje urnika:** pridobivanje urnika posameznega študenta v Python slovarju, primernem za pretvorbo v JSON in prikaz v aplikaciji.
- **Pretekli semestri:** podatki različnih semestrov so ločeni; ob uvozu novega semestra se prejšnji praviloma ohranijo.

## 2. Tehnologije

| Tehnologija | Vloga |
|---|---|
| Python | Programska logika scraperjev in uvoza |
| `httpx` | HTTP zahteve na FRI |
| `BeautifulSoup` | Razčlenjevanje HTML |
| PostgreSQL 17 | Relacijska podatkovna baza (lokalno v Dockerju) |
| SQLAlchemy | ORM, poizvedbe in transakcije |
| Alembic | Migracije podatkovnega modela |
| Docker Compose | Zagon razvojne baze |
| `pytest` | Avtomatski testi |
| `cron` | Dnevni zagon sinhronizacije na Ubuntu/Linux |

## 3. Struktura projekta

```text
moj_urnik_backend/
├── app/
│   ├── __init__.py
│   ├── db.py                 # povezava z bazo (DATABASE_URL)
│   ├── models.py             # SQLAlchemy modeli
│   ├── scraper.py            # globalni FRI scraper
│   ├── import_json.py        # uvoz globalnih podatkov
│   ├── student.py            # uradne dodelitve študenta
│   ├── sync.py               # dnevna sinhronizacija, aktualni semester
│   └── schedule.py           # branje osebnega urnika za API
├── alembic/
│   └── versions/            # migracije
├── tests/                   # avtomatski testi
├── fixtures/                # testni HTML
├── test_real_student.py     # lokalni integracijski test študenta
├── test_schedule.py         # lokalni preizkus branja urnika
├── alembic.ini
├── compose.yaml
├── requirements.txt
└── fri_urnik.json            # primer shranjenega globalnega posnetka
```

`sync.py`, `schedule.py` in lokalni testni skripti so bili dodani med nadaljnjim razvojem, zato niso nujno prisotni v prvem arhivu projekta.

## 4. Namestitev in prvi zagon

### 4.1 Zahteve

Potrebni so Python z `venv`, Docker z Docker Compose in dostop do spleta za prenos urnika.

```bash
cd ~/Namizje/moj_urnik_backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.2 PostgreSQL

```bash
docker compose up -d db
```

V terminalu nastavimo povezavo:

```bash
export DATABASE_URL='postgresql+psycopg://mojurnik:mojurnik@localhost:5432/mojurnik'
```

> Uporabniško ime in geslo sta primer **lokalne razvojne** konfiguracije iz `compose.yaml`. V produkciji uporabimo druga gesla in varno upravljanje skrivnosti. Spremenljivko `DATABASE_URL` je treba nastaviti tudi za vsak nov terminal ali jo naložiti iz ustrezno zaščitene konfiguracije okolja.

### 4.3 Migracije

```bash
alembic upgrade head
```

Migracije ustvarijo potrebne tabele, indekse in omejitve. Za že inicializirano bazo je ponoven `upgrade head` običajno brez sprememb.

### 4.4 Prvi uvoz podatkov

Če že imamo globalni posnetek `fri_urnik.json`:

```bash
python -m app.import_json fri_urnik.json
```

Če želimo najprej pridobiti nov posnetek s FRI:

```bash
python -m app.scraper --delay 1 --output fri_urnik.json
python -m app.import_json fri_urnik.json
```

Scraper je mogoče zagnati tudi neposredno kot `python app/scraper.py ...`.

**Primer uspešnega začetnega uvoza (zimski semester 2026/27):** 107 predmetov, 465 terminov, 920 skupin in 138 izvajalcev. To je rezultat dosedanjega testiranja, ne fiksna pričakovana vrednost za vse semestre.

## 5. Podatkovni model

| Tabela | Namen |
|---|---|
| `semester` | Semester, študijsko leto, vir podatkov |
| `predmet` | Predmet, šifra, naziv, URL in status aktivnosti |
| `termin` | Izvedba predmeta: dan, čas, tip, učilnica, kapaciteta, zasedenost |
| `skupina` | Skupina oziroma oznaka skupine |
| `termin_skupina` | Povezava N:M med termini in skupinami |
| `izvajalec` | Izvajalec/pedagog |
| `termin_izvajalec` | Povezava N:M med termini in izvajalci |
| `student` | Študent in njegova vpisna številka |
| `dodelitev` | **Uradna** dodelitev študenta posameznemu terminu |
| `zaklep` | Obvezen oziroma zaklenjen termin (globalno ali za študenta) |
| `sinhronizacija` | Zadnji uspešen globalni uvoz posamezne vrste podatkov |

Ključne povezave:

```text
semester ──< predmet ──< termin >── termin_skupina >── skupina
    │                        │
    └────────────────────────┤
                             ├──< termin_izvajalec >── izvajalec
student ──< dodelitev >──────┤
student ──< zaklep >─────────┘
```

- `predmet` in `termin` imata `semester_id`, zato se semestri ne mešajo.
- `dodelitev` je vezana na `student_id` in `termin_id` – semester izhaja iz termina.
- `zaklep` je vezan na termin; `student_id = NULL` lahko predstavlja globalni zaklep.
- `dodelitev` predstavlja **uradni FRI urnik**, ne končnega urnika po optimizaciji. Shranjevanje optimiziranih izbir je naloga integracije z optimizatorjem.
- V modelu `Sinhronizacija` se stolpec za vrsto uvoza imenuje **`tip`**, ne `vrsta`; timestamp se imenuje `zadnja_uspesna`.

## 6. Globalni scraper in uvoz

### `app/scraper.py`

Glavna funkcija je:

```python
podatki = scrape_all()
```

Vrne slovar s polji, kot so:

```python
{
    "vir": "https://urnik.fri.uni-lj.si/timetable/.../",
    "pridobljeno_utc": "...",
    "nepopolno": False,
    "napake": [],
    "predmeti": [...],
    "termini": [...]
}
```

Scraper najprej pridobi seznam predmetov, nato za vsak predmet njegove termine. Združi ponovljene termine z enakim FRI ID-jem in ohrani povezane skupine. Pri delnem prenosu označi rezultat kot nepopoln.

### `app/import_json.py`

```python
rezultat = import_data(session, podatki)
```

Uvoznik iz polja `vir` prepozna semester in po potrebi ustvari nov zapis v `semester`. Nato doda oziroma posodobi predmete, termine, skupine in izvajalce. Obstoječe predmete/termine, ki jih ni več v **popolnem** novem posnetku, označi kot `aktiven=False`, namesto da bi jih neposredno izbrisal. Po uspešnem uvozu posodobi `sinhronizacija` za `predmeti` in `termini`.

**Previdnost:** če scraper brez prijavljene napake vrne bistveno manj podatkov, bi uvoz lahko označil veliko zapisov kot neaktivne. V tej poenostavljeni različici se zanašamo na stabilnost portala in osnovne kontrole (`nepopolno`, `napake`, neprazni seznami). To je znana omejitev, ne popolna zaščita pred napačnim posnetkom.

## 7. Uvoz osebnega urnika

V `app/student.py` scraper prek URL-ja za dodelitve (`/allocations?student=...`) pridobi FRI identifikatorje terminov študenta. Nato jih poveže z že uvoženimi globalnimi termini v bazi.

Uporabni funkciji:

```python
ids = fetch_student_ids(vpisna_stevilka, semester)
rezultat = import_student_allocations(session, semester_slug, vpisna_stevilka, ids)
```

Med razvojem je bila dodana tudi ovojna funkcija:

```python
rezultat = uvozi_urnik_studenta(
    session=session,
    vpisna_stevilka=vpisna_stevilka,
    semester_slug=semester_slug
)
```

Ovojna funkcija ni del izvornega ZIP-a; preveri njeno prisotnost v lokalni `app/student.py`.

Za ročni uvoz s CLI iz izhodiščne različice:

```bash
python -m app.student fri-2026_2027-zimski TVOJA_VPISNA_STEVILKA
```

Osebne vpisne številke **ne zapisujemo v README, git ali javne dnevnike**. Za aplikacijo je primerneje, da jih prijavljeni uporabnik poda prek zaščitenega obrazca oz. jih backend pridobi iz ustrezne vezave na račun.

**Pomembno pri testiranju:** `session.flush()` še ne potrdi sprememb. `session.rollback()` jih razveljavi, `session.commit()` pa trajno shrani. Zato je bil med testiranjem viden urnik 13 terminov, čeprav študent po `rollback()` ni obstajal v bazi. Po trajnem uvozu je `schedule.py` uspešno prebral njegov urnik.

Pri ponovnem uvozu se posodobijo le študentove dodelitve iz **izbranega semestra**. Dodelitve drugih semestrov ostanejo nedotaknjene.

## 8. Dnevna sinhronizacija in aktualni semester

### `app/sync.py`

Glavne funkcije, razvite med delom:

| Funkcija | Namen |
|---|---|
| `potrebuje_osvezitev(zadnja_uspesna, interval_dni)` | Ali je od zadnjega uspešnega uvoza minil predpisani interval? |
| `pridobi_zadnjo_osvezitev(session, semester_id, vrsta)` | Prebere `Sinhronizacija.tip` in `zadnja_uspesna` |
| `preveri_osvezitve(session, semester_slug)` | Vrne, ali je potreben uvoz predmetov in terminov |
| `pridobi_aktualni_semester()` | Sledi preusmeritvi FRI in iz končnega URL-ja izlušči oznako semestra |
| `izvedi_osvezitev(session, force=False)` | Po potrebi zažene scraper in uvoz |

Primer preprostega preverjanja:

```python
stanje = preveri_osvezitve(session, semester_slug)
# npr. {"predmeti": False, "termini": True}
```

Projektna odločitev: **en celovit globalni uvoz vsakih 24 ur**, čeprav je bila prvotna ideja 30 dni za seznam predmetov in dnevno za termine. Ker globalni scraper že pridobi oboje, tako zmanjšamo kompleksnost kode. Če projektne zahteve strogo zahtevajo ločena intervala, je to treba uskladiti z ekipo/mentorjem.

Za ročni zagon:

```bash
python -m app.sync
```

Ko `pridobi_aktualni_semester()` obišče FRI začetno stran, `httpx` sledi preusmeritvi in prepozna na primer `fri-2026_2027-zimski`. **Oznaka semestra ni hardcodana v `main()`**.

Pri prvem pojavu novega semestra funkcija `preveri_osvezitve()` vrne, da je uvoz potreben. `import_data()` zna nato ustvariti zapis novega semestra. Pretekli predmeti, termini in študentove dodelitve ostanejo v bazi, ker so vezani na prejšnji semester. Ob prijavi študenta v nov semester je treba ponovno sprožiti uvoz njegovega osebnega urnika.

Pri klicu `import_data()` moramo uporabljati transakcijo:

```python
engine = engine_from_env()
with Session(engine) as session:
    with session.begin():
        rezultat = izvedi_osvezitev(session)
```

Če uvoz uspe, se spremembe potrdijo; ob napaki se razveljavijo. Funkcija mora zavrniti prenos, ki vsebuje napake, označbo `nepopolno` ali prazne podatke. Točen podpis `izvedi_osvezitev()` preveri v zadnji lokalni različici.

**Opomba o semestrih:** izvorni `SLUG_PATTERN` v `app/import_json.py` predvideva obliko `fri-LETO_LETO-zimski` ali `fri-LETO_LETO-poletni`. Če FRI uporabi drugačno poimenovanje ali obliko URL-ja, je treba prilagoditi prepoznavanje.

## 9. Branje urnika za FastAPI

### `app/schedule.py`

```python
urnik = get_student_schedule(session, student_id, semester_slug)
```

Funkcija iz tabel `student`, `dodelitev`, `termin` in `predmet` pridobi termine študenta ter jih vrne kot Python slovar. Rezultat vsebuje semester, število terminov, število predmetov in seznam terminov z dnevom, časom, tipom, učilnico ter skupinami. Časi so pretvorjeni v nize oblike `HH:MM` za lažje JSON kodiranje.

Poenostavljen primer odgovora (ilustracija):

```json
{
  "student_id": 2,
  "semester": "fri-2026_2027-zimski",
  "stevilo_terminov": 1,
  "stevilo_predmetov": 1,
  "termini": [
    {
      "predmet_naziv": "Vgrajeni sistemi",
      "dan": "TUE",
      "zacetek": "08:00",
      "konec": "11:00",
      "tip": "P",
      "skupine": ["P01"]
    }
  ]
}
```

Dejanski odgovor lahko vsebuje dodatna polja, kot so ID-ji, šifra predmeta, učilnica, kapaciteta in zasedenost.

Pri integraciji s FastAPI mora `student_id` izhajati iz **avtenticiranega uporabnika** in preverjenih pravic, ne iz poljubnega ID-ja v URL-ju. `get_student_schedule()` zgolj bere podatke; ne izvaja preverjanja dovoljenj.

## 10. Cron – samodejni dnevni zagon

Na Linuxu/Ubuntu se lahko sinhronizacija izvaja vsak dan ob 03:00 prek uporabniškega `crontab`:

```bash
crontab -e
```

**Pomembno:** `cron` običajno nima okolja interaktivnega terminala. Če `app/db.py` zahteva `DATABASE_URL`, mora biti ta na voljo tudi opravilu. En način je lokalni skript `run_sync.sh` z omejenimi pravicami in nalaganjem zaščitene konfiguracije okolja:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /home/uporabnik/Namizje/moj_urnik_backend
set -a
source /home/uporabnik/.config/moj-urnik/db.env
set +a
exec /home/uporabnik/Namizje/moj_urnik_backend/.venv/bin/python -m app.sync
```

Datoteka `~/.config/moj-urnik/db.env` lahko vsebuje `DATABASE_URL=...`; shranjena naj bo zunaj repozitorija, z dovoljenji `chmod 600`. Skript mora biti izvedljiv (`chmod +x run_sync.sh`).

Primer cron vrstice:

```cron
0 3 * * * /home/uporabnik/Namizje/moj_urnik_backend/run_sync.sh >> /home/uporabnik/Namizje/moj_urnik_backend/sync.log 2>&1
```

To je **primer pravilne nastavitve**, ne trditev, da lokalni cron že uporablja prav ta skript. Če je cron že nastavljen drugače, preverimo, da dejansko prenaša `DATABASE_URL` in uporablja pravi Python iz `.venv`.

Preverjanje opravila in dnevnika:

```bash
crontab -l
tail -n 50 sync.log
```

Za zagon morata biti računalnik in podatkovna baza vključena. Za produkcijo se opravilo nastavi na strežniku, kjer teče backend. `cron` ne izvede zamujenih opravil, kadar je računalnik ugasnjen.

## 11. Testiranje

### Avtomatski testi

```bash
python -m pytest -v
```

Izhodiščni projekt vsebuje `tests/test_import.py`; v lokalni nadgradnji je lahko nabor razširjen. Nabor testov vedno preveri glede na dejansko stanje projekta.

### Integracijski testi

```bash
python test_real_student.py
python test_schedule.py
```

Pri preizkusu dejanskega študentskega urnika je bil iz FRI uspešno pridobljen urnik s **13 termini in 7 predmeti**. Najprej smo uporabili `rollback()` (brez trajnega shranjevanja), nato `commit()`, da je bil urnik na voljo za branje iz druge seje.

### Preverjanje sinhronizacije

```bash
python -m app.sync
```

Preverimo, da se aktualni semester pravilno prepozna, globalni prenos zaključi, `import_data()` zapiše podatke in se ob naslednjem zagonu pred iztekom intervala ne izvaja nepotreben ponovni uvoz. Prisilno osvežitev (`force=True`) uporabimo le v namenskem testu in jo nato odstranimo iz običajnega zagona.

## 12. Znane omejitve in opozorila

1. **Vpisne številke so osebni podatki.** Ne zapisujemo jih v git, README ali dnevnike; uvoz izvajamo z ustreznim dovoljenjem.
2. **Razlika med uradno in optimizirano dodelitvijo:** `dodelitev` hrani uradno stanje FRI. Optimizacija potrebuje ločen način hranjenja izbranih terminov.
3. **Prekrivanja predavanj lahko že obstajajo na FRI.** V testnem urniku sta se dva petkova termina prekrivala. OR-Tools mora imeti jasno politiko za že obstoječa prekrivanja obveznih terminov.
4. **Kapaciteta ni nujno pravica do vpisa:** vrednosti s portala so informativne in jih mora optimizator razlagati skladno s pravili projekta.
5. **Spremembe HTML ali delni prenosi:** osnovno preverjanje ne zagotavlja, da je vsak neprazen posnetek popoln. Samodejno deaktiviranje odsotnih terminov zato zahteva previdnost.
6. **Prehod semestra:** stari podatki ostanejo; za nov semester je potreben nov globalni uvoz in pozneje uvoz osebnega urnika študenta.
7. **Avtomatizacija:** nastavljen `crontab` sam po sebi še ne dokazuje uspešnega izvajanja; preveriti je treba naslednji dejanski dnevni zagon in `sync.log`.

## 13. Integracija z ostalimi člani ekipe

| Del ekipe | Kaj uporabi |
|---|---|
| FastAPI / prijava | `engine_from_env()`, SQLAlchemy `Session`, `uvozi_urnik_studenta(...)`, `get_student_schedule(...)` |
| React | JSON, ki ga vrne endpoint za študentov urnik |
| OR-Tools optimizator | `termin`, `skupina`, `dodelitev`, `zaklep`, kapacitete in zasedenosti |
| Administracija / razporejevalnik | `python -m app.sync` ali ustrezna storitev/scheduler |

**Pred integracijo** je treba preveriti pooblastila uporabnikov, način vezave prijavljenega računa na `student`, politiko obstoječih prekrivanj in kje se shranjuje optimiziran urnik.

## 14. Hiter pregled ukazov

```bash
# Aktiviraj razvojno okolje
source .venv/bin/activate

# Zaženi bazo
docker compose up -d db

# Nastavi povezavo do baze (lokalni razvoj)
export DATABASE_URL='postgresql+psycopg://mojurnik:mojurnik@localhost:5432/mojurnik'

# Migracije
alembic upgrade head

# Pridobi in uvozi globalni posnetek
python -m app.scraper --delay 1 --output fri_urnik.json
python -m app.import_json fri_urnik.json

# Sinhronizacija aktualnega semestra
python -m app.sync

# Testi
python -m pytest -v
python test_schedule.py

# Preveri cron
crontab -l
```

---

**Stanje projekta:** globalni in študentski uvoz, branje osebnega urnika ter ročna sinhronizacija so bili uspešno preizkušeni med razvojem. Integracija s FastAPI, React in OR-Tools je ločeno ekipno delo.
