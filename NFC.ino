// Bibliotecas necessárias para o ESP8266
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h> // Para fazer requisições HTTP
#include <WiFiClient.h>
#include <ArduinoJson.h>       // Para criar o JSON payload

// Bibliotecas para o PN532 via I2C
#include <Wire.h>
#include <PN532_I2C.h>
#include <PN532.h>
#include <NfcAdapter.h> // Não é estritamente necessário se usar apenas PN532.h/PN532_I2C.h

// ======================================================================
// --- CONFIGURAÇÕES OBRIGATÓRIAS ---
// ======================================================================

// --- 1. Configurações de Rede ---
const char* ssid = "LRSBD";
const char* password = "lrsbd2023";

// --- 2. Configuração da API ---
const char* serverAddress = "162.120.186.86"; 
const int serverPort = 5000;

// --- 3. Configurações do Leitor PN532 (I2C) ---
// O PN532 usando I2C no ESP8266 utiliza os pinos padrão de I2C:
// SDA -> D2
// SCL -> D1
// Não há necessidade de configurar pinos RST/SS.

PN532_I2C pn532i2c(Wire);
PN532 nfc(pn532i2c);

// ======================================================================

// Protótipos de função
void connectToWiFi();
void baterPonto(String idUsuario);
int enviarRequisicao(String endpoint, String idUsuario);

void setup() {
  Serial.begin(115200);
  Serial.println("\n[Leitor de Ponto NFC - ESP8266 com PN532] Iniciando...");

  connectToWiFi();

  // --- Inicialização do PN532 ---
  Wire.begin(); // Inicia o I2C
  nfc.begin();

  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println(">>> ERRO: Não encontrou o chip PN53x!");
    delay(1000);
    // Em produção, você pode querer reiniciar ou entrar em modo de falha.
    // ESP.restart(); 
  } else {
    // Exibe a versão do firmware, como no seu primeiro código
    Serial.print("Found chip PN5"); Serial.println((versiondata>>24) & 0xFF, HEX); 
    Serial.print("Firmware ver. "); Serial.print((versiondata>>16) & 0xFF, DEC); 
    Serial.print('.'); Serial.println((versiondata>>8) & 0xFF, DEC);
  }
  
  nfc.setPassiveActivationRetries(0xFF); // Tenta ler a cada 0xFF vezes
  nfc.SAMConfig(); // Configura a placa para ler tags

  Serial.println("\n>>> Aproxime o cartão NFC para bater o ponto <<<");
}

void loop() {
  // Garante que o WiFi esteja conectado
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado. Tentando reconectar...");
    connectToWiFi();
  }

  handleCardRead();
  delay(50); // Pequena pausa
}

void handleCardRead() {
  boolean success;
  // Buffer para armazenar o UID (máximo 7 bytes para ISO14443A)
  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 };  
  uint8_t uidLength;                        
  
  // Tenta ler um cartão tipo ISO14443A (Mifare, etc.) com timeout de 50ms
  success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, &uid[0], &uidLength, 50);
  
  if (success) {
    
    Serial.println("======================================");
    Serial.println("Cartão NFC detectado!");
    
    // 3. Obter o UID (ID Único) do cartão e formatar como String
    String cardUid = "";
    for (byte i = 0; i < uidLength; i ++) {
      // Adiciona um "0" à esquerda se for menor que 0x10
      cardUid += (uid[i] < 0x10 ? "0" : "");
      // Converte para hexadecimal, igual ao código MFRC522 original (sem separador)
      cardUid += String(uid[i], HEX); 
    }
    cardUid.toUpperCase();
    
    Serial.print("ID do Usuário (UID): ");
    Serial.println(cardUid);

    // 4. Tentar bater o ponto (Lógica "Tenta-Entrada-Depois-Saída")
    baterPonto(cardUid);

    // 5. Espera até que o cartão seja removido para evitar leituras duplicadas
    // O timeout de 50ms na função permite que o loop continue rapidamente.
    Serial.println("Ponto registrado. Aguardando remoção do cartão...");
    while (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, &uid[0], &uidLength, 50)) {
        delay(100);
    }
    
    Serial.println("Cartão removido.");
    Serial.println("======================================\n");
    Serial.println(">>> Aproxime o cartão NFC para bater o ponto <<<");
  }
}

/*
 * Função principal para bater o ponto (mantida a mesma lógica)
 */
void baterPonto(String idUsuario) {
  
  // --- TENTATIVA DE ENTRADA ---
  Serial.println("Tentando registrar ENTRADA...");
  int httpCodeEntrada = enviarRequisicao("/ponto/entrada", idUsuario);

  if (httpCodeEntrada == 201) { // 201 = "Created" (Sucesso na API)
    Serial.println(">>> SUCESSO: Entrada registrada!");
    return; 
  } 
  
  if (httpCodeEntrada == 400) {
    // Código 400 (Bad Request) significa "Usuário já possui ponto em aberto"
    Serial.println("ENTRADA falhou (usuário já está 'dentro').");
    Serial.println("Tentando registrar SAÍDA...");
    
    // --- TENTATIVA DE SAÍDA ---
    int httpCodeSaida = enviarRequisicao("/ponto/saida", idUsuario);

    if (httpCodeSaida == 200) { // 200 = "OK" (Sucesso na API)
      Serial.println(">>> SUCESSO: Saída registrada!");
      return;
    } else {
      // A saída falhou por outro motivo (404, 500, etc)
      Serial.print(">>> ERRO: Saída falhou. Código HTTP: ");
      Serial.println(httpCodeSaida);
    }
  } else {
    // A entrada falhou por outro motivo (500, etc)
    Serial.print(">>> ERRO: Entrada falhou. Código HTTP: ");
    Serial.println(httpCodeEntrada);
  }
}

/*
 * Função helper para enviar a requisição POST com JSON (mantida a mesma lógica)
 */
int enviarRequisicao(String endpoint, String idUsuario) {
  WiFiClient client;
  HTTPClient http;

  // Monta a URL completa: "http://192.168.1.105:5000/ponto/entrada"
  String url = "http://" + String(serverAddress) + ":" + String(serverPort) + endpoint;
  
  Serial.print("POST para: ");
  Serial.println(url);

  if (http.begin(client, url)) {
    http.addHeader("Content-Type", "application/json");

    // Cria o corpo (payload) JSON: {"id_usuario": "UID_DO_CARTAO"}
    StaticJsonDocument<100> jsonDoc; // Documento JSON pequeno
    jsonDoc["id_usuario"] = idUsuario;
    
    String jsonPayload;
    serializeJson(jsonDoc, jsonPayload);
    Serial.print("Payload: ");
    Serial.println(jsonPayload);

    // Envia a requisição POST
    int httpCode = http.POST(jsonPayload);

    // Feedback no Serial Monitor
    if (httpCode > 0) {
      String response = http.getString();
      Serial.print("Resposta da API: ");
      Serial.println(response);
    } else {
      Serial.print("Falha na requisição HTTP: ");
      Serial.println(http.errorToString(httpCode).c_str());
    }

    http.end();
    return httpCode; 

  } else {
    Serial.println("ERRO: Não foi possível iniciar o cliente HTTP.");
    return -1; 
  }
}

/*
 * Função helper para conectar ao WiFi (mantida a mesma lógica)
 */
void connectToWiFi() {
  Serial.print("Conectando a ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("\nWiFi conectado!");
  Serial.print("Endereço IP (ESP8266): ");
  Serial.println(WiFi.localIP());
}
