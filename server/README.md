# Lotify Server

Dieser Server ist das Backend für die Lotify-App.

- Empfängt Nachrichten per HTTP (z.B. curl/wget)
- Nachrichten werden an registrierte Geräte (Public Key) weitergeleitet
- Verwaltung der Public Keys (Registrierung durch die App)
- Nachrichten werden verschlüsselt übertragen
- Bereitstellung als Docker-Container

## Endpunkte (geplant)
- `/register`   – Registrierung eines Public Keys
- `/send`       – Nachricht an ein Gerät senden (Header, Content, CDN-ID, Public Key)
- `/cdn/<id>`   – CDN-Inhalte bereitstellen (optional)

## Starten

```sh
docker build -t lotify-server .
docker run -p 8080:8080 lotify-server
``` 