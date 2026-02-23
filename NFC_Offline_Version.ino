// ======================================================================
// LEITOR DE PONTO NFC - OFFLINE FIRST (RTC + LCD + LITTLEFS)
// ======================================================================

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <PN532_I2C.h>
#include <PN532.h>
#include <LittleFS.h>
#include <time.h> 
#include <RTClib.h> 
#include <LiquidCrystal_I2C.h>

// --- 1. Configurações de Rede ---
const char* ssid = "Rede Maluso";
const char* password = "malusomen";

// --- 2. Configuração da API ---
const char* serverAddress = "10.26.98.59";
const int serverPort = 5000;

// --- 3. Configurações de Tempo (NTP) ---
const long  gmtOffset_sec = -10800;
const int   daylightOffset_sec = 0;

// --- 4. Configurações do Hardware ---
PN532_I2C pn532i2c(Wire);
PN532 nfc(pn532i2c);
RTC_DS1307 rtc; 
LiquidCrystal_I2C lcd(0x27, 16, 2); 

const char* FILE_PATH = "/fila_ponto.txt";
unsigned long lastSyncAttempt = 0;
const unsigned long syncInterval = 10000;

// Protótipos
void connectToWiFi();
void handleCardRead();
void salvarOffline(String cardUid, time_t timestamp);
void processarFilaOffline();
int enviarRequisicaoLogicaCompleta(String cardUid, long timestamp);
int enviarRequisicao(String endpoint, String cardUid, long timestamp);

void setup() {
  Serial.begin(115200);
  
  Wire.begin();
  
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Iniciando...");

  if (!LittleFS.begin()) {
    Serial.println("ERRO: LittleFS!");
    lcd.clear();
    lcd.print("Erro LittleFS");
    return;
  }
  
  if (!rtc.begin()) {
    Serial.println("ERRO: RTC!");
  }
  
  // Ajusta o RTC caso esteja parado ou com data inválida
  if (!rtc.isrunning() || rtc.now().year() < 2024) {
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  }

  nfc.begin();
  if (!nfc.getFirmwareVersion()) {
    Serial.println("ERRO: PN53x!");
    lcd.clear();
    lcd.print("Erro NFC");
    while (1) { delay(10); }
  }
   
  nfc.setPassiveActivationRetries(0xFF);
  nfc.SAMConfig();

  connectToWiFi();
  lcd.clear();
}

void loop() {
  // Exibe mensagem de espera
  lcd.setCursor(0, 0);
  lcd.print("Aproxime o card ");
  
  // Exibe relógio atualizado no LCD
  DateTime agora = rtc.now();
  char horaFormatada[17];
  sprintf(horaFormatada, "%02d/%02d  %02d:%02d:%02d", agora.day(), agora.month(), agora.hour(), agora.minute(), agora.second());
  lcd.setCursor(0, 1);
  lcd.print(horaFormatada);

  handleCardRead();
  
  if (WiFi.status() == WL_CONNECTED && (millis() - lastSyncAttempt > syncInterval)) {
    processarFilaOffline();
    lastSyncAttempt = millis();
  }
  delay(50);
}

void handleCardRead() {
  boolean success;
  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 };   
  uint8_t uidLength;                       
    
  success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, &uid[0], &uidLength, 50);
  
  if (success) {
    lcd.clear();
    lcd.print("Lendo...");

    String cardUid = "";
    for (byte i = 0; i < uidLength; i ++) {
      cardUid += (uid[i] < 0x10 ? "0" : "");
      cardUid += String(uid[i], HEX);
    }
    cardUid.toUpperCase();
    
    time_t now = rtc.now().unixtime();
    
    lcd.setCursor(0, 0);
    lcd.print("ID Detectado:");
    lcd.setCursor(0, 1);
    lcd.print(cardUid);

    salvarOffline(cardUid, now);
    
    // Espera 2 segundos para o usuário ver o ID no visor
    delay(2000); 
    
    // Aguarda o cartão ser removido
    while (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, &uid[0], &uidLength, 50)) {
        delay(100);
    }
    lcd.clear();
  }
}

void salvarOffline(String cardUid, time_t timestamp) {
  File file = LittleFS.open(FILE_PATH, "a");
  if (file) {
    file.print(cardUid);
    file.print(";");
    file.println(timestamp); 
    file.close();
    Serial.println("Ponto salvo offline.");
  }
}

void processarFilaOffline() {
  if (!LittleFS.exists(FILE_PATH)) return;
  File file = LittleFS.open(FILE_PATH, "r");
  if (!file) return;

  if (file.size() == 0) {
    file.close();
    LittleFS.remove(FILE_PATH);
    return;
  }

  String pendingData = "";
  while (file.available()) {
    pendingData += (char)file.read();
  }
  file.close();

  String remainingData = ""; 
  int processedCount = 0;
  int strIndex = 0;

  while (strIndex < pendingData.length()) {
    int endIndex = pendingData.indexOf('\n', strIndex);
    if (endIndex == -1) endIndex = pendingData.length();
    
    String line = pendingData.substring(strIndex, endIndex);
    line.trim();
    
    if (line.length() > 0) {
      int sep = line.indexOf(';');
      String lineUID = "";
      long rawTs = 0;

      if (sep != -1) {
          lineUID = line.substring(0, sep);
          rawTs = line.substring(sep + 1).toInt();
      } else {
          lineUID = line;
      }

      int result = enviarRequisicaoLogicaCompleta(lineUID, rawTs);
      if (result != -1) {
        processedCount++;
      } else {
        remainingData += line + "\n";
      }
    }
    strIndex = endIndex + 1;
  }

  if (processedCount > 0) {
    if (remainingData.length() == 0) {
      LittleFS.remove(FILE_PATH);
    } else {
      File fileWrite = LittleFS.open(FILE_PATH, "w"); 
      fileWrite.print(remainingData);
      fileWrite.close();
    }
  }
}

int enviarRequisicaoLogicaCompleta(String cardUid, long timestamp) {
  int httpCode = enviarRequisicao("/ponto/entrada", cardUid, timestamp);
  if (httpCode == 201) return 201;
  
  if (httpCode == 400) {
    int httpCodeSaida = enviarRequisicao("/ponto/saida", cardUid, timestamp);
    if (httpCodeSaida == 200) return 200;
  }
  return httpCode;
}

int enviarRequisicao(String endpoint, String cardUid, long timestamp) {
  WiFiClient client;
  HTTPClient http;
  String url = "http://" + String(serverAddress) + ":" + String(serverPort) + endpoint;
  
  if (http.begin(client, url)) {
    http.addHeader("Content-Type", "application/json");
    StaticJsonDocument<200> doc;
    doc["card_uid"] = cardUid;
    doc["timestamp"] = timestamp;
    String payload;
    serializeJson(doc, payload);
    int code = http.POST(payload);
    http.end();
    return code;
  }
  return -1;
}

void connectToWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(ssid, password);
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 15) { 
    delay(500); retries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    configTime(gmtOffset_sec, daylightOffset_sec, "pool.ntp.org", "time.nist.gov");
    time_t now = time(nullptr);
    int r = 0;
    while (now < 100000 && r < 10) { delay(500); now = time(nullptr); r++; }
    if (now > 100000) {
      struct tm * ti = localtime(&now);
      rtc.adjust(DateTime(ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday, ti->tm_hour, ti->tm_min, ti->tm_sec));
    }
  }
}
