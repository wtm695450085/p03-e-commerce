# ProSport — patch na przesłanych plikach index(3).html i style(3).css

Zmiany:
- static/index.html: tylko sekcja HERO
- static/css/style.css: tylko dopisany blok CSS dla prawego obrazka HERO
- static/images/hero/wojciech-hero.png: obrazek HERO

Nie rusza:
- /js/app.js
- backendu
- API
- bazy
- produktów
- dockera

Wgranie na VPS:

cd /srv/mlops/apps/p03-e-commerc
unzip -o prosport_PATCH_on_uploaded_files.zip -d .

Jeśli static jest podpięty jako volume, kontenera nie trzeba przebudowywać.
