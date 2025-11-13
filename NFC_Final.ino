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
const char* ssid = "Rede Maluso";
const char* password = "malusomen";

// --- 2. Configuração da API ---
// IP da sua máquina Windows rodando a API
const char* serverAddress = "10.230.155.59";
const int serverPort = 5000;

// --- 3. Configurações do Leitor PN532 (I2C) ---
// SDA -> D2
// SCL -> D1
PN532_I2C pn532i2c(Wire);
PN532 nfc(pn532i2c);

// ======================================================================

// Protótipos de função
void connectToWiFi();
void baterPonto(String cardUid); // MUDANÇA: 'idUsuario' agora é 'cardUid'
int enviarRequisicao(String endpoint, String cardUid); // MUDANÇA: 'idUsuario' agora é 'cardUid'

void setup() {
  Serial.begin(115200);
  Serial.println("\n[Leitor de Ponto NFC v2 - ESP8266 com PN532] Iniciando...");

  connectToWiFi();

  // --- Inicialização do PN532 ---
  Wire.begin(); // Inicia o I2C
  nfc.begin();

  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println(">>> ERRO: Não encontrou o chip PN53x!");
    while (1) { delay(10); } // Trava aqui se não achar o leitor
  } else {
    Serial.print("Found chip PN5"); Serial.println((versiondata>>24) & 0xFF, HEX); 
    Serial.print("Firmware ver. "); Serial.print((versiondata>>16) & 0xFF, DEC); 
    Serial.print('.'); Serial.println((versiondata>>8) & 0xFF, DEC);
  }
  
  nfc.setPassiveActivationRetries(0xFF);
  nfc.SAMConfig();

  Serial.println("\n>>> Aproxime o cartão NFC para bater o ponto <<<");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado. Tentando reconectar...");
    connectToWiFi();
  }
  handleCardRead();
  delay(50);
}

void handleCardRead() {
  boolean success;
  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 };  
  uint8_t uidLength;                        
  
  success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, &uid[0], &uidLength, 50);
  
  if (success) {
    Serial.println("======================================");
    Serial.println("Cartão NFC detectado!");
    
    String cardUid = "";
    for (byte i = 0; i < uidLength; i ++) {
      cardUid += (uid[i] < 0x10 ? "0" : "");
      cardUid += String(uid[i], HEX); 
    }
    cardUid.toUpperCase();
    
    Serial.print("ID do Usuário (UID): ");
    Serial.println(cardUid);

    // 4. Tentar bater o ponto
    baterPonto(cardUid);

    // 5. Espera até que o cartão seja removido
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
 * Função principal para bater o ponto (Lógica "Tenta-Entrada-Depois-Saída")
 */
void baterPonto(String cardUid) { // MUDANÇA: Renomeado para 'cardUid' para clareza
  
  // --- TENTATIVA DE ENTRADA ---
  Serial.println("Tentando registrar ENTRADA...");
  // Passa o cardUid para a função de requisição
  int httpCodeEntrada = enviarRequisicao("/ponto/entrada", cardUid);

  if (httpCodeEntrada == 201) {
    Serial.println(">>> SUCESSO: Entrada registrada!");
    // (Aqui podemos adicionar o feedback de LED Verde)
    return; 
  } 
  
  if (httpCodeEntrada == 400) {
    Serial.println("ENTRADA falhou (Pode ser 'Já está dentro' ou 'card_uid' faltando).");
    Serial.println("Tentando registrar SAÍDA...");
    
    // --- TENTATIVA DE SAÍDA ---
    int httpCodeSaida = enviarRequisicao("/ponto/saida", cardUid);

    if (httpCodeSaida == 200) {
      Serial.println(">>> SUCESSO: Saída registrada!");
      // (Aqui podemos adicionar o feedback de LED Azul)
      return;
    } else {
      Serial.print(">>> ERRO: Saída falhou. Código HTTP: ");
      Serial.println(httpCodeSaida);
      // (Aqui podemos adicionar o feedback de LED Vermelho)
    }
  } else {
    // Outros erros (404 = Cartão não cadastrado, 500 = Erro de API, -1 = Falha de conexão)
    Serial.print(">>> ERRO: Entrada falhou. Código HTTP: ");
    Serial.println(httpCodeEntrada);
    // (Aqui podemos adicionar o feedback de LED Vermelho)
  }
}

/*
 * Função helper para enviar a requisição POST com JSON
 */
int enviarRequisicao(String endpoint, String cardUid) { // MUDANÇA: Renomeado para 'cardUid'
  WiFiClient client;
  HTTPClient http;

  String url = "http://" + String(serverAddress) + ":" + String(serverPort) + endpoint;
  
  Serial.print("POST para: ");
  Serial.println(url);

  if (http.begin(client, url)) {
    http.addHeader("Content-Type", "application/json");

    // Cria o corpo (payload) JSON
    StaticJsonDocument<100> jsonDoc;
    
    // --- MUDANÇA CRÍTICA AQUI ---
    // A API V2 espera "card_uid", não "id_usuario"
    jsonDoc["card_uid"] = cardUid;
    
    String jsonPayload;
    serializeJson(jsonDoc, jsonPayload);
    Serial.print("Payload: ");
    Serial.println(jsonPayload);

    int httpCode = http.POST(jsonPayload);

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
 * Função helper para conectar ao WiFi
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
