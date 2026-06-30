# ProSport — kosmetyczna poprawka HERO

Zmiany:
1. Tytuł:
   Sklep sportowy
   inżyniera AI Wojciecha Moszczyńskiego.

2. Tekst:
   Wybierz dowolnego klienta i zobacz, jak działa system rekomendacji.
   Obserwuj, jak system zwiększa Twoją sprzedaż.

3. Usunięto czerwoną ramkę.
4. Usunięto napis: Demo AI · sport · rekomendacje.
5. Zdjęcie Wojciecha jest większe i jednocześnie stanowi tło HERO.
6. Kafelki działów w HERO są w jednej linii.

Nie rusza:
- /js/app.js
- API
- backendu
- bazy
- produktów
- Dockera

Wgranie na VPS:

cd /srv/mlops/apps/p03-e-commerc
unzip -o prosport_HERO_cosmetic_update.zip -d .

Jeśli static jest jako volume, nie trzeba przebudowywać kontenera.
