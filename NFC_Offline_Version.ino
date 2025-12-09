// ======================================================================
// LEITOR DE PONTO NFC - OFFLINE FIRST (COM TIMESTAMP)
// ======================================================================

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <PN532_I2C.h>
#include <PN532.h>
#include <LittleFS.h>
#include <time.h> // BIBLIOTECA DE TEMPO

// --- 1. Configurações de Rede ---
const char* ssid = "Rede Maluso";
const char* password = "malusomen";

// --- 2. Configuração da API ---
const char* serverAddress = "10.230.155.59";
const int serverPort = 5000;

// --- 3. Configurações de Tempo (NTP) ---
// Fuso horário em segundos (GMT -3 para Ceará/Brasil = -10800)
const long  gmtOffset_sec = -10800; 
const int   daylightOffset_sec = 0; // Sem horário de verão

// --- 4. Configurações do Hardware ---
PN532_I2C pn532i2c(Wire);
PN532 nfc(pn532i2c);

// Nome do arquivo onde salvaremos os pontos pendentes
const char* FILE_PATH = "/fila_ponto.txt";

// Controle de tempo
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
  Serial.println("\n[Leitor Ponto - Offline First] Iniciando...");

  if (!LittleFS.begin()) {
    Serial.println("ERRO: Falha ao montar LittleFS!");
    return;
  }

  Wire.begin();
  nfc.begin();
   
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("ERRO: PN53x não encontrado!");
    while (1) { delay(10); }
  }
   
  nfc.setPassiveActivationRetries(0xFF);
  nfc.SAMConfig();

  // Conecta e tenta pegar a hora
  connectToWiFi();

  Serial.println("\n>>> SISTEMA PRONTO: Aproxime o cartão <<<");
}

void loop() {
  handleCardRead();

  // Sincronização em Background
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
    Serial.println("\n--- Cartão Detectado ---");
     
    String cardUid = "";
    for (byte i = 0; i < uidLength; i ++) {
      cardUid += (uid[i] < 0x10 ? "0" : "");
      cardUid += String(uid[i], HEX); 
    }
    cardUid.toUpperCase();
    
    // CAPTURA A HORA ATUAL
    time_t now = time(nullptr);
    Serial.print("UID: "); Serial.println(cardUid);
    Serial.print("Timestamp (Unix): "); Serial.println(now);

    // Verifica se a hora é válida (maior que ano 2020)
    // Se for < 1600000000, provavelmente o relógio não sincronizou (está em 1970)
    if (now < 100000) {
        Serial.println("ALERTA: Relógio do sistema desatualizado! Salvando sem hora precisa.");
    }

    // SALVA OFFLINE COM O TIMESTAMP
    salvarOffline(cardUid, now);
     
    Serial.println("STATUS: Salvo na memória.");
     
    while (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, &uid[0], &uidLength, 50)) {
        delay(100);
    }
    Serial.println("--- Fim da Leitura ---\n");
  }
}

/*
 * Salva UID e Timestamp separados por ";"
 * Exemplo no arquivo: F432A1;1701234567
 */
void salvarOffline(String cardUid, time_t timestamp) {
  File file = LittleFS.open(FILE_PATH, "a"); 
  if (!file) {
    Serial.println("ERRO CRÍTICO: Falha ao abrir arquivo!");
  } else {
    // Formato CSV simples: UID;TIMESTAMP
    file.print(cardUid);
    file.print(";");
    file.println(timestamp); 
    file.close();
    Serial.println(">> Ponto armazenado na fila (LittleFS).");
  }
}

/*
 * Processa o arquivo linha por linha, separando UID e Hora
 */
/*
 * Lê o arquivo, tenta enviar linha por linha e limpa o que foi enviado.
 * CORREÇÃO: Ajuste na exibição da data no Serial.
 */
void processarFilaOffline() {
  if (!LittleFS.exists(FILE_PATH)) return; 

  File file = LittleFS.open(FILE_PATH, "r");
  if (!file) return;

  if (file.size() == 0) {
    file.close();
    LittleFS.remove(FILE_PATH);
    return;
  }

  Serial.println("\nIniciando sincronização...");

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
      int separatorIndex = line.indexOf(';');
      
      String lineUID = "";
      long rawTimestamp = 0; // Mantemos como long (ou int32) para ler do arquivo

      if (separatorIndex != -1) {
          lineUID = line.substring(0, separatorIndex);
          // Lê o número como long
          rawTimestamp = line.substring(separatorIndex + 1).toInt();
      } else {
          lineUID = line;
      }

      Serial.print("Enviando UID: "); Serial.print(lineUID);
      
      // --- CORREÇÃO AQUI ---
      // Criamos uma variável time_t real e atribuímos o valor do long a ela
      time_t correctTime = (time_t)rawTimestamp; 
      Serial.print(" | Data: "); Serial.print(ctime(&correctTime)); 
      // ---------------------
      
      bool sentSuccess = false;
      // Passamos o rawTimestamp original para a função de envio
      int result = enviarRequisicaoLogicaCompleta(lineUID, rawTimestamp);
      
      if (result != -1) {
        sentSuccess = true;
        processedCount++;
      }
      
      if (!sentSuccess) {
        Serial.println("Falha de rede. Mantendo na fila.");
        remainingData += line + "\n";
      }
    }
    
    strIndex = endIndex + 1;
  }

  if (processedCount > 0) {
    if (remainingData.length() == 0) {
      LittleFS.remove(FILE_PATH); 
      Serial.println("Todos os pontos enviados com sucesso!");
    } else {
      File fileWrite = LittleFS.open(FILE_PATH, "w"); 
      fileWrite.print(remainingData);
      fileWrite.close();
      Serial.print("Sincronização parcial. Pontos restantes salvos.");
    }
  } else {
     Serial.println("Nenhuma conexão estabelecida nesta tentativa.");
  }
}

int enviarRequisicaoLogicaCompleta(String cardUid, long timestamp) {
  int httpCode = enviarRequisicao("/ponto/entrada", cardUid, timestamp);

  if (httpCode == 201) {
    Serial.println("   -> Entrada registrada (API).");
    return 201;
  } 
   
  if (httpCode == 400) {
    Serial.println("   -> Tentando Saída...");
    int httpCodeSaida = enviarRequisicao("/ponto/saida", cardUid, timestamp);
    if (httpCodeSaida == 200) {
      Serial.println("   -> Saída registrada (API).");
      return 200;
    }
    return httpCodeSaida;
  }

  return httpCode;
}

int enviarRequisicao(String endpoint, String cardUid, long timestamp) {
  WiFiClient client;
  HTTPClient http;
  String url = "http://" + String(serverAddress) + ":" + String(serverPort) + endpoint;

  if (http.begin(client, url)) {
    http.addHeader("Content-Type", "application/json");
    
    StaticJsonDocument<200> jsonDoc;
    jsonDoc["card_uid"] = cardUid;
    jsonDoc["timestamp"] = timestamp; // Envia o Unix Timestamp (Int)

    String jsonPayload;
    serializeJson(jsonDoc, jsonPayload);

    int httpCode = http.POST(jsonPayload);
    http.end();
    return httpCode; 
  } else {
    return -1; 
  }
}

void connectToWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
   
  Serial.print("Conectando WiFi: "); Serial.println(ssid);
  WiFi.begin(ssid, password);
   
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 15) { // Aumentei um pouco o tempo
    delay(500);
    Serial.print(".");
    retries++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Conectado!");
    Serial.println(WiFi.localIP());
    
    // INICIA E SINCRONIZA O TEMPO (NTP)
    Serial.println("Sincronizando relógio NTP...");
    configTime(gmtOffset_sec, daylightOffset_sec, "pool.ntp.org", "time.nist.gov");
    
    // Aguarda um pouco para sincronizar
    time_t now = time(nullptr);
    int retryTime = 0;
    while (now < 100000 && retryTime < 5) {
        delay(500);
        Serial.print(".");
        now = time(nullptr);
        retryTime++;
    }
    Serial.println("\nRelógio sincronizado!");
    Serial.println(ctime(&now));

  } else {
    Serial.println("\nWiFi não conectado (Relógio pode estar incorreto).");
  }
}
