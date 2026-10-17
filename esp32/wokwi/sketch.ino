#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DallasTemperature.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_system.h>

namespace {

constexpr uint8_t PH_PIN = 34;
constexpr uint8_t TURBIDITY_PIN = 35;
constexpr uint8_t TDS_PIN = 32;
constexpr uint8_t WATER_TEMP_PIN = 4;
constexpr uint8_t AMBIENT_TEMP_PIN = 5;
constexpr uint8_t OLED_SDA_PIN = 21;
constexpr uint8_t OLED_SCL_PIN = 22;
constexpr uint8_t OLED_ADDRESS = 0x3C;
constexpr int OLED_WIDTH = 128;
constexpr int OLED_HEIGHT = 64;
constexpr unsigned long SAMPLE_INTERVAL_MS = 15000;
constexpr unsigned long DISPLAY_PAGE_INTERVAL_MS = 3000;
constexpr uint8_t DISPLAY_PAGE_COUNT = 5;
constexpr uint8_t PH_HISTORY_SIZE = 30;
constexpr uint8_t ADC_SAMPLE_COUNT = 20;
constexpr float ADC_REFERENCE_VOLTAGE = 3.3f;
constexpr float ADC_MAX_READING = 4095.0f;
constexpr float TURBIDITY_SLOPE = -1120.0f;
constexpr float TURBIDITY_INTERCEPT = 3000.0f;
constexpr float TDS_FACTOR = 1.0f;
constexpr float PH7_VOLTAGE = 2.50f;
constexpr float PH_SLOPE = 5.70f;

constexpr char API_URL[] =
    "https://aqua-sense-flame.vercel.app/api/ingestion/reading";

struct UploadTarget {
  const char* deviceId;
  long riverId;
};

constexpr UploadTarget UPLOAD_TARGETS[] = {
    {"WOKWI-DEMO-BAKAS", 2},
    {"WOKWI-DEMO-MATIKTIK", 3},
    {"WOKWI-DEMO-KANYAKAN", 4},
    {"WOKWI-DEMO-MARAMO", 5},
};
constexpr uint8_t UPLOAD_TARGET_COUNT =
    sizeof(UPLOAD_TARGETS) / sizeof(UPLOAD_TARGETS[0]);
uint8_t selectedTargetIndex = 0;

constexpr char WIFI_SSID[] = "Wokwi-GUEST";
constexpr char WIFI_PASSWORD[] = "";

constexpr char ROOT_CA_CERT[] PROGMEM = R"PEM(
-----BEGIN CERTIFICATE-----
MIIFVzCCAz+gAwIBAgINAgPlk28xsBNJiGuiFzANBgkqhkiG9w0BAQwFADBHMQsw
CQYDVQQGEwJVUzEiMCAGA1UEChMZR29vZ2xlIFRydXN0IFNlcnZpY2VzIExMQzEU
MBIGA1UEAxMLR1RTIFJvb3QgUjEwHhcNMTYwNjIyMDAwMDAwWhcNMzYwNjIyMDAw
MDAwWjBHMQswCQYDVQQGEwJVUzEiMCAGA1UEChMZR29vZ2xlIFRydXN0IFNlcnZp
Y2VzIExMQzEUMBIGA1UEAxMLR1RTIFJvb3QgUjEwggIiMA0GCSqGSIb3DQEBAQUA
A4ICDwAwggIKAoICAQC2EQKLHuOhd5s73L+UPreVp0A8of2C+X0yBoJx9vaMf/vo
27xqLpeXo4xL+Sv2sfnOhB2x+cWX3u+58qPpvBKJXqeqUqv4IyfLpLGcY9vXmX7w
Cl7raKb0xlpHDU0QM+NOsROjyBhsS+z8CZDfnWQpJSMHobTSPS5g4M/SCYe7zUjw
TcLCeoiKu7rPWRnWr4+wB7CeMfGCwcDfLqZtbBkOtdh+JhpFAz2weaSUKK0Pfybl
qAj+lug8aJRT7oM6iCsVlgmy4HqMLnXWnOunVmSPlk9orj2XwoSPwLxAwAtcvfaH
szVsrBhQf4TgTM2S0yDpM7xSma8ytSmzJSq0SPly4cpk9+aCEI3oncKKiPo4Zor8
Y/kB+Xj9e1x3+naH+uzfsQ55lVe0vSbv1gHR6xYKu44LtcXFilWr06zqkUspzBmk
MiVOKvFlRNACzqrOSbTqn3yDsEB750Orp2yjj32JgfpMpf/VjsPOS+C12LOORc92
wO1AK/1TD7Cn1TsNsYqiA94xrcx36m97PtbfkSIS5r762DL8EGMUUXLeXdYWk70p
aDPvOmbsB4om3xPXV2V4J95eSRQAogB/mqghtqmxlbCluQ0WEdrHbEg8QOB+DVrN
VjzRlwW5y0vtOUucxD/SVRNuJLDWcfr0wbrM7Rv1/oFB2ACYPTrIrnqYNxgFlQID
AQABo0IwQDAOBgNVHQ8BAf8EBAMCAYYwDwYDVR0TAQH/BAUwAwEB/zAdBgNVHQ4E
FgQU5K8rJnEaK0gnhS9SZizv8IkTcT4wDQYJKoZIhvcNAQEMBQADggIBAJ+qQibb
C5u+/x6Wki4+omVKapi6Ist9wTrYggoGxval3sBOh2Z5ofmmWJyq+bXmYOfg6LEe
QkEzCzc9zolwFcq1JKjPa7XSQCGYzyI0zzvFIoTgxQ6KfF2I5DUkzps+GlQebtuy
h6f88/qBVRRiClmpIgUxPoLW7ttXNLwzldMXG+gnoot7TiYaelpkttGsN/H9oPM4
7HLwEXWdyzRSjeZ2axfG34arJ45JK3VmgRAhpuo+9K4l/3wV3s6MJT/KYnAK9y8J
ZgfIPxz88NtFMN9iiMG1D53Dn0reWVlHxYciNuaCp+0KueIHoI17eko8cdLiA6Ef
MgfdG+RCzgwARWGAtQsgWSl4vflVy2PFPEz0tv/bal8xa5meLMFrUKTX5hgUvYU/
Z6tGn6D/Qqc6f1zLXbBwHSs09dR2CQzreExZBfMzQsNhFRAbd03OIozUhfJFfbdT
6u9AWpQKXCBfTkBdYiJ23//OYb2MI3jSNwLgjt7RETeJ9r/tSQdirpLsQBqvFAnZ
0E6yove+7u7Y/9waLd64NnHi/Hm3lCXRSHNboTXns5lndcEZOitHTtNCjv0xyBZm
2tIMPNuzjsmhDYAPexZ3FL//2wmUspO8IFgV6dtxQ/PeEMMA3KgqlbbC1j+Qa3bb
bP6MvPJwNQzcmRk13NfIRmPVNnGuV/u3gm3c
-----END CERTIFICATE-----
)PEM";

Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
OneWire waterTemperatureWire(WATER_TEMP_PIN);
OneWire ambientTemperatureWire(AMBIENT_TEMP_PIN);
DallasTemperature waterTemperatureSensor(&waterTemperatureWire);
DallasTemperature ambientTemperatureSensor(&ambientTemperatureWire);
unsigned long lastSampleMs = 0;
unsigned long lastDisplayPageMs = 0;
bool displayReady = false;
uint8_t displayPage = 0;
float phHistory[PH_HISTORY_SIZE] = {};
uint8_t phHistoryCount = 0;
uint8_t phHistoryNext = 0;

struct WaterReading {
  float ph;
  float turbidity;
  float tds;
  float waterTemperature;
  float ambientTemperature;
  float tss;
  float particleLevel;
  float clarity;
  float conductivity;
  float ionicContent;
  float salinity;
  float acidity;
  float alkalinity;
  float phStability;
  float changeRate;
  float thermalAnomaly;
};

WaterReading currentReading = {};
bool readingAvailable = false;

int clampRounded(float value, int minimum, int maximum) {
  return constrain(static_cast<int>(lroundf(value)), minimum, maximum);
}

void rememberPH(float ph) {
  phHistory[phHistoryNext] = ph;
  phHistoryNext = (phHistoryNext + 1) % PH_HISTORY_SIZE;
  if (phHistoryCount < PH_HISTORY_SIZE) {
    ++phHistoryCount;
  }
}

float calculatePHStability(float ph) {
  float minimumPH = ph;
  float maximumPH = ph;
  for (uint8_t index = 0; index < phHistoryCount; ++index) {
    minimumPH = min(minimumPH, phHistory[index]);
    maximumPH = max(maximumPH, phHistory[index]);
  }
  return clampRounded(100.0f - (maximumPH - minimumPH) * 2.0f, 0, 100);
}

float readAverageVoltage(uint8_t pin) {
  uint32_t totalAdc = 0;

  for (uint8_t sample = 0; sample < ADC_SAMPLE_COUNT; ++sample) {
    totalAdc += analogRead(pin);
    delay(3);
  }

  const float averageAdc =
      static_cast<float>(totalAdc) / ADC_SAMPLE_COUNT;
  return averageAdc * ADC_REFERENCE_VOLTAGE / ADC_MAX_READING;
}

void drawReading(const WaterReading& reading, const char* uploadStatus) {
  if (!displayReady) {
    return;
  }

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("AquaSense ");
  display.print(displayPage + 1);
  display.print("/");
  display.println(DISPLAY_PAGE_COUNT);

  switch (displayPage) {
    case 0:
      display.print("pH ");
      display.print(reading.ph, 2);
      display.print("  TDS ");
      display.print(reading.tds, 0);
      display.println(" ppm");
      display.print("Turbidity ");
      display.print(reading.turbidity, 1);
      display.println(" NTU");
      display.print("Water ");
      display.print(reading.waterTemperature, 1);
      display.println(" C");
      break;
    case 1:
      display.println("Turbidity indicators");
      display.print("TSS est ");
      display.print(reading.tss, 0);
      display.println(" mg/L*");
      display.print("Particles ");
      display.print(reading.particleLevel, 0);
      display.println("%");
      display.print("Clarity ");
      display.print(reading.clarity, 0);
      display.println("%");
      break;
    case 2:
      display.println("TDS indicators");
      display.print("Conduct ");
      display.print(reading.conductivity, 0);
      display.println(" uS/cm*");
      display.print("Ionic score ");
      display.print(reading.ionicContent, 0);
      display.println("%");
      display.print("Salinity ");
      display.print(reading.salinity, 1);
      display.println(" ppt*");
      break;
    case 3:
      display.println("pH indicators");
      display.print("Acidity ");
      display.print(reading.acidity, 0);
      display.println("%");
      display.print("Alkalinity ");
      display.print(reading.alkalinity, 0);
      display.println("%");
      display.print("pH stability ");
      display.print(reading.phStability, 0);
      display.println("%");
      break;
    default:
      display.println("Temperature insights");
      display.print("Ambient ");
      display.print(reading.ambientTemperature, 1);
      display.println(" C");
      display.print("Change ");
      display.print(reading.changeRate, 2);
      display.println(" C/min");
      display.print("Thermal ");
      display.println(reading.thermalAnomaly > 0 ? "ANOMALY" : "normal");
      break;
  }
  display.println(uploadStatus);
  display.display();
}

void refreshDisplay() {
  if (!readingAvailable) {
    return;
  }
  if (millis() - lastDisplayPageMs >= DISPLAY_PAGE_INTERVAL_MS) {
    lastDisplayPageMs = millis();
    displayPage = (displayPage + 1) % DISPLAY_PAGE_COUNT;
  }
  drawReading(currentReading, "Live simulation");
}

bool connectWiFi(unsigned long timeoutMs) {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);

  const unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - startedAt < timeoutMs) {
    delay(100);
  }

  return WiFi.status() == WL_CONNECTED;
}

const char* sendReading(const WaterReading& reading) {
  const UploadTarget& target = UPLOAD_TARGETS[selectedTargetIndex];

  if (!connectWiFi(10000)) {
    Serial.println("Upload failed: Wi-Fi is not connected.");
    return "Wi-Fi offline";
  }

  char payload[512];
  const int payloadLength = snprintf(
      payload,
      sizeof(payload),
      "{\"device_id\":\"%s\",\"river_id\":%ld,"
      "\"ph_value\":%.0f,\"turbidity_ntu\":%.0f,\"tds_ppm\":%.0f,"
      "\"tss\":%.0f,\"particle_level\":%.0f,\"clarity\":%.0f,"
      "\"conductivity\":%.0f,\"ionic_content\":%.0f,\"salinity\":%.0f,"
      "\"acidity\":%.0f,\"alkalinity\":%.0f,\"ph_stability\":%.0f,"
      "\"temperature_c\":%.0f,\"ambient_temperature\":%.0f,"
      "\"change_rate\":%.0f,\"thermal_anomaly\":%.0f}",
      target.deviceId,
      target.riverId,
      reading.ph * 100.0f,
      reading.turbidity,
      reading.tds,
      reading.tss,
      reading.particleLevel,
      reading.clarity,
      reading.conductivity,
      reading.ionicContent,
      reading.salinity,
      reading.acidity,
      reading.alkalinity,
      reading.phStability,
      reading.waterTemperature * 100.0f,
      reading.ambientTemperature * 100.0f,
      reading.changeRate * 100.0f,
      reading.thermalAnomaly);

  if (payloadLength < 0 ||
      static_cast<size_t>(payloadLength) >= sizeof(payload)) {
    Serial.println("Upload failed: JSON payload exceeded its buffer.");
    return "Payload error";
  }

  Serial.printf("Uploading synthetic sample for %s (river %ld).\n",
                target.deviceId,
                target.riverId);

  WiFiClientSecure tlsClient;
  tlsClient.setCACert(ROOT_CA_CERT);

  HTTPClient http;
  if (!http.begin(tlsClient, API_URL)) {
    Serial.println("Upload failed: could not initialize HTTPS.");
    return "HTTPS error";
  }

  http.setTimeout(20000);
  http.addHeader("Content-Type", "application/json");
  const int statusCode = http.POST(
      reinterpret_cast<uint8_t*>(payload),
      static_cast<size_t>(payloadLength));

  if (statusCode < 0) {
    Serial.printf("Upload failed: %s\n",
                  HTTPClient::errorToString(statusCode).c_str());
    http.end();
    return "Upload failed";
  }

  const String response = http.getString();
  Serial.printf("Upload HTTP %d: %s\n",
                statusCode,
                response.c_str());
  http.end();

  if (statusCode >= 200 && statusCode < 300) {
    return "Upload OK";
  }
  if (statusCode == 403) {
    return "Register sensor";
  }
  return "Server error";
}

void sampleAndReport() {
  const float phVoltage = readAverageVoltage(PH_PIN);
  const float turbidityVoltage = readAverageVoltage(TURBIDITY_PIN);
  const float tdsVoltage = readAverageVoltage(TDS_PIN);

  // Wokwi potentiometers simulate analog modules; calibrate real sensors
  // against their datasheets before using their readings operationally.
  currentReading.ph = constrain(
      7.0f + (PH7_VOLTAGE - phVoltage) * PH_SLOPE, 0.0f, 14.0f);
  currentReading.turbidity = clampRounded(
      TURBIDITY_SLOPE * turbidityVoltage + TURBIDITY_INTERCEPT, 0, 3000);

  waterTemperatureSensor.requestTemperatures();
  ambientTemperatureSensor.requestTemperatures();
  currentReading.waterTemperature =
      waterTemperatureSensor.getTempCByIndex(0);
  currentReading.ambientTemperature =
      ambientTemperatureSensor.getTempCByIndex(0);
  if (currentReading.waterTemperature == DEVICE_DISCONNECTED_C ||
      currentReading.ambientTemperature == DEVICE_DISCONNECTED_C) {
    Serial.println("Water or ambient temperature sensor not detected.");
    return;
  }

  const float compensation = max(
      0.1f, 1.0f + 0.02f * (currentReading.waterTemperature - 25.0f));
  const float compensatedVoltage = tdsVoltage / compensation;
  const float voltageSquared = compensatedVoltage * compensatedVoltage;
  const float voltageCubed = voltageSquared * compensatedVoltage;
  currentReading.tds = clampRounded(
      (133.42f * voltageCubed - 255.86f * voltageSquared +
       857.39f * compensatedVoltage) *
          0.5f * TDS_FACTOR,
      0,
      10000);
  currentReading.tss =
      clampRounded(currentReading.turbidity * 0.5f, 0, 10000);
  currentReading.particleLevel =
      clampRounded((currentReading.turbidity / 1000.0f) * 100.0f, 0, 100);
  currentReading.clarity = 100.0f - currentReading.particleLevel;
  currentReading.conductivity =
      clampRounded(currentReading.tds * 2.0f, 0, 20000);
  currentReading.ionicContent =
      clampRounded(currentReading.tds / 10.0f, 0, 100);
  currentReading.salinity =
      clampRounded(currentReading.tds / 1000.0f, 0, 100);
  currentReading.acidity =
      clampRounded((7.0f - currentReading.ph) / 7.0f * 100.0f, 0, 100);
  currentReading.alkalinity =
      clampRounded((currentReading.ph - 7.0f) / 7.0f * 100.0f, 0, 100);
  const float storedPH = currentReading.ph * 100.0f;
  currentReading.phStability = calculatePHStability(storedPH);
  rememberPH(storedPH);

  static float previousWaterTemperature = currentReading.waterTemperature;
  static unsigned long previousTemperatureMs = millis();
  const unsigned long now = millis();
  const float elapsedMinutes =
      static_cast<float>(now - previousTemperatureMs) / 60000.0f;
  currentReading.changeRate =
      elapsedMinutes > 0.0f
          ? (currentReading.waterTemperature - previousWaterTemperature) /
                elapsedMinutes
          : 0.0f;
  currentReading.thermalAnomaly =
      currentReading.waterTemperature > 40.0f ||
              currentReading.waterTemperature < 5.0f ||
              fabsf(currentReading.waterTemperature -
                    currentReading.ambientTemperature) > 10.0f
          ? 1.0f
          : 0.0f;
  previousWaterTemperature = currentReading.waterTemperature;
  previousTemperatureMs = now;
  readingAvailable = true;

  Serial.printf(
      "Simulation reading: pH=%.2f, turbidity=%.1f NTU*, TDS=%.0f ppm*, "
      "water=%.2f C, ambient=%.2f C\n",
      currentReading.ph,
      currentReading.turbidity,
      currentReading.tds,
      currentReading.waterTemperature,
      currentReading.ambientTemperature);

  const char* uploadStatus = sendReading(currentReading);
  drawReading(currentReading, uploadStatus);
  lastDisplayPageMs = millis();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);

  displayReady = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS);
  if (!displayReady) {
    Serial.println("OLED initialization failed.");
  }

  waterTemperatureSensor.begin();
  ambientTemperatureSensor.begin();
  Serial.println("AquaSense ESP32 prototype starting.");
  Serial.println("Analog pH, turbidity, and TDS inputs are simulated.");

  connectWiFi(15000);
  selectedTargetIndex = esp_random() % UPLOAD_TARGET_COUNT;
  const UploadTarget& target = UPLOAD_TARGETS[selectedTargetIndex];
  Serial.printf("This simulation run is assigned to %s (river %ld).\n",
                target.deviceId,
                target.riverId);
  sampleAndReport();
  lastSampleMs = millis();
  lastDisplayPageMs = millis();
}

void loop() {
  if (millis() - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = millis();
    sampleAndReport();
  }
  refreshDisplay();
  delay(20);
}
