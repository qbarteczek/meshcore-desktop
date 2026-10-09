# MeshCore Desktop – pomoc

Aplikacja do obsługi urządzeń sieci radiowej MeshCore z komputera z Windows: rozmowy, konfiguracja, zdalne zarządzanie repeaterami i narzędzia diagnostyczne.

# 1. Połączenie z urządzeniem

Kliknij „Połącz…” u góry okna i wybierz sposób:

• Bluetooth – kliknij „Szukaj urządzeń”, wybierz swoje z listy, wpisz PIN (domyślny PIN MeshCore to 123456; urządzenia z ekranem pokazują własny) i kliknij „Połącz”. Parowanie z PIN-em aplikacja robi sama.
• USB (port szeregowy) – dla urządzeń z firmware „companion USB”. Wybierz port COM.
• Sieć (TCP/Wi-Fi) – dla urządzeń z firmware „companion Wi-Fi”. Podaj adres i port (zwykle 5000).

Urządzenie obsługuje jedno połączenie naraz: przed połączeniem rozłącz aplikację MeshCore w telefonie.
Połączone urządzenia są zapamiętywane na liście „Urządzenie:” – wybranie pozycji łączy ponownie.

# 2. Wiadomości

Lista po lewej pokazuje kanały oraz kontakty, z którymi już rozmawiałeś. Żeby napisać do kogoś nowego, wpisz fragment nazwy w polu „Szukaj kontaktu”.
Przy wiadomościach prywatnych widać, czy odbiorca potwierdził odbiór („✓ doręczono”). Wiadomości na kanałach nie mają potwierdzeń.
Kropka ● oznacza nieprzeczytane wiadomości. Historia jest zapisywana osobno dla każdego urządzenia.

# 3. Kontakty

Pełna lista kontaktów zapisanych w urządzeniu, z filtrem po nazwie i typie (klient, repeater, serwer pokoju, czujnik). Kliknięcie nagłówka kolumny sortuje.
„Porządki…” usuwa kontakty niesłyszane od podanej liczby dni – przydatne, gdy lista jest pełna i urządzenie nie przyjmuje nowych. Kontakty z historią rozmów i cel testu łącza nie są usuwane.

# 4. Zdalne zarządzanie

Repeatery, serwery pokojów i czujniki konfiguruje się przez sieć radiową, za pośrednictwem podłączonego urządzenia:
1. wybierz węzeł z listy (można wpisać fragment nazwy),
2. wpisz hasło administratora węzła i kliknij „Zaloguj”,
3. użyj przycisków „Status”, „Telemetria”, „Sąsiedzi” albo wpisz polecenie CLI (np. „ver”, „get radio”, „set name …”).

Odpowiedzi przychodzą przez radio, więc mogą pojawić się po kilkunastu sekundach albo wcale, jeśli węzeł jest poza zasięgiem.

# 5. Test łącza

Cyklicznie wysyła krótką wiadomość do wybranego kontaktu i zapisuje, czy odbiorca ją potwierdził (ACK), po jakim czasie, jaką trasą, oraz sygnał i napięcie baterii nadawcy. Wyniki trafiają do pliku CSV.
Opcjonalnie: jeśli po stronie odbiorcy działa mostek publikujący plik traces.json, aplikacja odczyta z niego SNR/RSSI odebranej wiadomości. Wymaga to włączenia „sondy na kanale”, czyli dodatkowej wiadomości na wybranym kanale – używaj z umiarem na kanałach publicznych.
Test działa tylko wtedy, gdy aplikacja jest uruchomiona i połączona.

# 6. Urządzenie

Nazwa, pozycja, moc nadawania, parametry radia, PIN Bluetooth i kanały podłączonego urządzenia.
Uwaga: błędne parametry radia odcinają urządzenie od sieci. „Kopia ustawień…” zapisuje ustawienia, kanały (z kluczami) i listę kontaktów do pliku JSON; „Przywróć z kopii…” przywraca nazwę, pozycję, moc i kanały.

# 7. Konsola USB

Repeater, serwer pokoju lub czujnik podłączony kablem USB ma tekstową konsolę poleceń. Wybierz port, kliknij „Otwórz” i wpisuj polecenia (np. „ver”, „get radio”, „set tx 20”, „reboot”).
To osobne połączenie – nie wymaga urządzenia „companion”.

# 8. Deweloper

Podgląd na żywo odebranych pakietów radiowych (SNR, RSSI, typ, trasa) i wszystkich zdarzeń biblioteki. W polu polecenia można wywołać dowolną komendę biblioteki meshcore, np. get_bat(), get_stats_packets(), send_advert(True).
„Folder danych” otwiera katalog z konfiguracją, historią i dziennikami.

# 9. Ustawienia

Język (polski/angielski), automatyczne łączenie przy starcie, dźwięk powiadomień, uruchamianie z Windows, lista zapamiętanych urządzeń.

# Najczęstsze problemy

• „Brak połączenia … Insufficient Authentication” – zły PIN. Połącz ponownie przez „Połącz…” i podaj właściwy.
• Urządzenia nie widać w skanowaniu – jest połączone z telefonem albo wyłączone; rozłącz aplikację w telefonie.
• Brak potwierdzeń wiadomości – odbiorca poza zasięgiem; spróbuj „Resetuj trasę” w zakładce Kontakty.

# Licencja i podziękowania

MeshCore Desktop jest wolnym oprogramowaniem na licencji MIT. Korzysta z bibliotek meshcore (meshcore_py), bleak i pyserial. Projekt nie jest oficjalnym produktem MeshCore.
Kod źródłowy: https://github.com/qbarteczek/meshcore-desktop
