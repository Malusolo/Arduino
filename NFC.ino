/*
 * Código C++/Arduino para Leitor de Ponto NFC com ESP8266 (NodeMCU/LoLin)
 *
 * Funcionalidade:
 * 1. Conecta ao WiFi.
 * 2. Lê o UID de um cartão NFC (MFRC522).
 * 3. Envia o UID para a API Flask de relógio de ponto.
 * 4. Tenta registrar ENTRADA. Se já estiver "dentro", tenta registrar SAÍDA.
 */

// Bibliotecas necessárias para o ESP8266
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h> // Para fazer requisições HTTP
#include <WiFiClient.h>
#include <ArduinoJson.h>       // Para criar o JSON payload
#include <SPI.h>               // Para comunicação com o MFRC522
#include <MFRC522.h>           // Para ler o NFC

// ======================================================================
// --- CONFIGURAÇÕES OBRIGATÓRIAS ---
// ======================================================================

// --- 1. Configurações de Rede ---
const char* ssid = "NOME_DA_SUA_REDE_WIFI";
const char* password = "SENHA_DA_SUA_REDE_WIFI";

// --- 2. Configuração da API ---
// IMPORTANTE: NÃO USE "localhost" ou "127.0.0.1"!
// Coloque o IP da sua máquina que está rodando a API Python.
// (Ex: "192.168.1.105")
const char* serverAddress = "COLOQUE_O_IP_DO_SEU_PC_AQUI"; 
const int serverPort = 5000;

// --- 3. Configurações dos Pinos do MFRC522 (NFC) ---
// Pinos para a placa LoLin ESP8266 da foto
// SCK  -> D5
// MISO -> D6
// MOSI -> D7
// SDA  -> D4 (SS)
// RST  -> D3

#define RST_PIN D3 // Pino RST
#define SS_PIN  D4 // Pino SDA (SS)

MFRC522 mfrc522(SS_PIN, RST_PIN); // Cria a instância do leitor

// ======================================================================

void setup() {
  Serial.begin(115200);
  Serial.println("\n[Leitor de Ponto NFC - ESP8266] Iniciando...");

  connectToWiFi();

  SPI.begin();       // Inicia o barramento SPI
  mfrc522.PCD_Init(); // Inicia o leitor MFRC522
  
  Serial.print("Status do Leitor MFRC522: ");
  mfrc522.PCD_DumpVersionToSerial(); // Mostra versão do firmware

  Serial.println("\n>>> Aproxime o cartão NFC para bater o ponto <<<");
}

void loop() {
  // Garante que o WiFi esteja conectado
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado. Tentando reconectar...");
    connectToWiFi();
  }

  // 1. Procura por novos cartões
  if ( ! mfrc522.PICC_IsNewCardPresent()) {
    delay(50); // Pequena pausa para não sobrecarregar
    return;
  }

  // 2. Seleciona um dos cartões (caso vários estejam presentes)
  if ( ! mfrc522.PICC_ReadCardSerial()) {
    delay(50);
    return;
  }

  Serial.println("======================================");
  Serial.println("Cartão NFC detectado!");

  // 3. Obter o UID (ID Único) do cartão
  String cardUid = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    // Adiciona um "0" à esquerda se for menor que 0x10 (ex: "0A" em vez de "A")
    cardUid += (mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
    cardUid += String(mfrc522.uid.uidByte[i], HEX);
  }
  cardUid.toUpperCase();
  
  Serial.print("ID do Usuário (UID): ");
  Serial.println(cardUid);

  // 4. Tentar bater o ponto (Lógica "Tenta-Entrada-Depois-Saída")
  baterPonto(cardUid);

  // 5. Pausa para evitar leitura duplicada
  mfrc522.PICC_HaltA(); // Coloca o cartão em modo "parado"
  mfrc522.PCD_StopCrypto1(); // Para a criptografia
  
  Serial.println("Ponto registrado. Aguardando 3 segundos...");
  Serial.println("======================================\n");
  delay(3000); // Pausa de 3 segundos
  
  Serial.println(">>> Aproxime o cartão NFC para bater o ponto <<<");
}

/*
 * Função principal para bater o ponto
 */
void baterPonto(String idUsuario) {
  
  // --- TENTATIVA DE ENTRADA ---
  Serial.println("Tentando registrar ENTRADA...");
  int httpCodeEntrada = enviarRequisicao("/ponto/entrada", idUsuario);

  if (httpCodeEntrada == 201) { // 201 = "Created" (Sucesso na API)
    Serial.println(">>> SUCESSO: Entrada registrada!");
    // (Aqui você pode acender um LED verde, por exemplo)
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
      // (Aqui você pode acender um LED azul, por exemplo)
      return;
    } else {
      // A saída falhou por outro motivo (404, 500, etc)
      Serial.print(">>> ERRO: Saída falhou. Código HTTP: ");
      Serial.println(httpCodeSaida);
      // (Aqui você pode acender um LED vermelho)
    }
  } else {
    // A entrada falhou por outro motivo (500, etc)
    Serial.print(">>> ERRO: Entrada falhou. Código HTTP: ");
    Serial.println(httpCodeEntrada);
    // (Aqui você pode acender um LED vermelho)
  }
}

/*
 * Função helper para enviar a requisição POST com JSON
 */
int enviarRequisicao(String endpoint, String idUsuario) {
  WiFiClient client;
  HTTPClient http;

  // Monta a URL completa: "http://192.168.1.105:5000/ponto/entrada"
  String url = "http://" + String(serverAddress) + ":" + String(serverPort) + endpoint;
  
  Serial.print("POST para: ");
  Serial.println(url);

  // Sintaxe correta para o ESP8266
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
    return httpCode; // Retorna o código (ex: 201, 400, 404)

  } else {
    Serial.println("ERRO: Não foi possível iniciar o cliente HTTP.");
    return -1; // Código de erro local (falha do ESP)
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
