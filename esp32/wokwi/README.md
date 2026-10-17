# AquaSense ESP32 Wokwi prototype

This project simulates an ESP32 water-quality node with:

- An SSD1306 128x64 I2C OLED.
- Three potentiometers standing in for analog pH, turbidity, and TDS modules.
- Two DS18B20 sensors for water and ambient temperature.
- Five rotating OLED pages showing primary readings and their derived
  indicators.

The potentiometers simulate analog pH, turbidity, and TDS module outputs. The
sketch averages 20 ADC samples and applies the calibration formulas and default
coefficients below; these are examples, not universal sensor constants:

- ADC voltage: `average_adc * 3.3 / 4095`.
- Turbidity: `clamp(-1120 * voltage + 3000, 0, 3000)` NTU.
- pH: `clamp(7 + (2.50 - voltage) * 5.70, 0, 14)`.
- TDS: `clamp((133.42*v^3 - 255.86*v^2 + 857.39*v) * 0.5 * TDS_FACTOR, 0, 10000)`,
  where `v = voltage / max(0.1, 1 + 0.02 * (water_temp_c - 25))` and
  `TDS_FACTOR = 1.0`.

TSS, particle level, clarity, conductivity, ionic content, salinity, acidity,
alkalinity, pH stability, temperature change rate, and thermal anomaly are
derived indicators, not additional physical sensors. Do not use simulated
readings for research or operational decisions. Calibrate real sensors against
their datasheets and standards; verify analog outputs never exceed the ESP32's
3.3 V input limit.

## Run in Wokwi

1. Open [Wokwi's ESP32 project editor](https://wokwi.com/projects/new/esp32).
2. Replace `sketch.ino` with the contents of this folder's `sketch.ino`.
3. Replace `diagram.json` with this folder's `diagram.json`.
4. Add the libraries listed in `libraries.txt` using Library Manager.
5. Start the simulation. Adjust the pH, turbidity, and TDS potentiometers and
   the water/ambient DS18B20 parts. The OLED rotates through all five pages.

The sketch is configured to post to the deployed AquaSense Flask endpoint.
Wokwi connects through the `Wokwi-GUEST` network; a real ESP32 must use the
actual Wi-Fi credentials. HTTPS certificate validation uses the Google Trust
Services GTS Root R1 CA, matching the deployed Vercel endpoint. If the
endpoint's certificate chain changes, replace this root with its trusted CA;
do not disable TLS verification.

## Connect to AquaSense

The firmware posts primary and derived measurement fields as JSON to
`POST /api/ingestion/reading`. Its ADC conversions, calibration formulas,
derived indicators, temperature scaling, and anomaly checks follow the
documented ESP32 calculations. pH and temperatures are sent ×100, matching the
database convention; the endpoint converts them for assessment and display.
The Flask endpoint saves the reading and assessment, derives quality severity
from turbidity and thermal anomaly, applies active threshold rules, and creates
applicable alerts. The ESP32 does not connect directly to Supabase or contain
database credentials.

1. At startup, the simulator randomly selects one of the four explicitly
   synthetic demo river/sensor registrations: Bakas, Matiktik, Kanyakan, or
   Maramo. Every reading in that simulation run goes to the selected river.
   Restart the simulation to randomly select a different river. The separate
   `AQUASENSE-ESP32-001` registration remains available for the original
   Wokwi-only test river.
2. Ensure the endpoint's `DATABASE_URL` is configured for your Supabase
   PostgreSQL database. A local endpoint at `127.0.0.1` is not reachable from
   the cloud-hosted Wokwi simulator.

Do not put production credentials or a production device secret in a public
Wokwi project. The current ingestion endpoint identifies the device by ID and
does not yet validate a per-device API key; add device-key authentication before
using it as an internet-facing production endpoint.
