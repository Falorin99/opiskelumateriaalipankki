# StudyHub – opiskelumateriaalipankki

StudyHub on Flaskilla ja SQLite-tietokannalla toteutettava opiskelumateriaalien
jakamissovellus.

## Sovelluksen toiminnot

- Käyttäjä pystyy luomaan tunnuksen ja kirjautumaan sisään sovellukseen.
- Käyttäjä pystyy lisäämään opiskelumateriaaleja sekä muokkaamaan ja poistamaan omiaan.
- Käyttäjä näkee kaikkien käyttäjien lisäämät opiskelumateriaalit.
- Käyttäjä pystyy etsimään opiskelumateriaaleja nimen tai kuvauksen perusteella.
- Materiaalille valitaan aihealue ja materiaalin tyyppi tietokannan luokitteluista.
- Käyttäjäsivut näyttävät käyttäjän materiaalit ja tilastot (suunnitteilla).
- Käyttäjä voi kommentoida materiaaleja (suunnitteilla).

NYKYISET toiminnot:
- rekisteröityminen, kirjautuminen ja uloskirjautuminen
- materiaalien luominen, muokkaaminen ja poistaminen (vain omat materiaalit)
- kaikkien materiaalien selaaminen ja yksittäisen materiaalin avaaminen
- haku materiaalin nimen tai kuvauksen perusteella
- aihealueen ja materiaalityypin valinta tietokantaan tallennetuista vaihtoehdoista
- salasanan tiivistys, CSRF-suojaus, syötteiden tarkistus ja SQL-parametrit

**Myöhemmin toteutettavat lopulliset perusvaatimukset:** käyttäjäsivut ja tilastot,
useiden luokitusarvojen valinta saman luokittelun sisällä sekä kommentit
(toissijainen tietokohde).

## Asennus ja käynnistäminen

Tarvitset Python 3.12:n (tai muun Flask 3:n kanssa yhteensopivan Python-version)
sekä SQLite3-komentorivityökalun.

Kloonaa repositorio tai lataa projektin tiedostot samaan kansioon.
Suorita seuraavat komennot **projektikansiossa**:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sqlite3 studyhub.db < schema.sql
sqlite3 studyhub.db < init.sql
flask --app app run
```

Avaa selaimessa **http://127.0.0.1:5000**.

Tietokanta `studyhub.db` luodaan paikallisesti SQL-tiedostoista. **Tietokantatiedostoa
ei lisätä GitHubiin.** Jos sinulla on jo vanhan version `studyhub.db`, älä korvaa sitä:
ota varmuuskopio ennen muutoksia. Tämän version taulurakenne on yhteensopiva
edellisen StudyHub-version kanssa; uudelleenluontia ei tarvita.

## Testaus selaimessa

1. Avaa etusivu ja luo tunnus kohdasta **Rekisteröidy**.
2. Lisää materiaali: nimi, kuvaus, https-linkki, aihealue ja materiaalityyppi.
3. Tarkista, että uusi materiaali näkyy etusivulla ja sitä klikkaamalla avautuu tietosivu.
4. Valitse materiaalin tietosivulta **Muokkaa**, muuta nimeä ja tallenna.
5. Hae uutta nimeä etusivun hakukentällä. Kokeile myös hakua, joka ei tuota tuloksia.
6. Valitse omalta materiaalilta **Poista** ja vahvista poistaminen.
7. Kirjaudu ulos ja luo toinen käyttäjätunnus. Varmista, että muiden materiaalit näkyvät
   mutta niiden muokkaaminen ja poistaminen ei ole sallittua.

Automatisoidut testit (Flaskin mukana tuleva test client ja Pythonin `unittest`):

```bash
python3 -m unittest discover -s tests -v
```

## Tiedostorakenne

- `app.py` – Flask-reitit, lomakkeiden tarkistus ja CSRF-suojaus
- `db.py` – SQLite-yhteys ja SQL-kyselyiden suorittaminen
- `users.py` – käyttäjien tietokantatoiminnot
- `materials.py` – materiaalien tietokantatoiminnot
- `config.py` – paikalliset asetukset
- `schema.sql` ja `init.sql` – taulut ja luokittelujen alkuarvot
- `templates/` – HTML-sivupohjat
- `static/style.css` – itse kirjoitettu CSS
- `tests/` – automaattiset testit

Sovellus on toteutettu kurssin esimerkkisovelluksen rakennetta mukaillen:
Flask, suorat SQL-kyselyt ja erilliset HTML- ja CSS-tiedostot.
Sovellus on tarkoitettu paikalliseen kehityskäyttöön. Älä julkaise Flaskin
kehityspalvelinta suoraan internetiin.
