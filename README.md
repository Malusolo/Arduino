# Sistema de Ponto IoT com NFC e API Flask

## Descrição do Projeto
Sistema completo de relógio de ponto inteligente que utiliza ESP8266 com leitor NFC para registrar entradas e saídas através de uma API Flask.

## Como Funciona
1. Usuário aproxima cartão NFC do leitor
2. ESP8266 lê o UID do cartão
3. Conecta via WiFi e envia dados para API
4. API processa e registra no banco MySQL
5. Retorna confirmação para o dispositivo

## Tecnologias Utilizadas

### Hardware
- ESP8266 (NodeMCU)
- Leitor NFC PN532
- Conexão I2C

### Software
- Python com Flask
- MySQL
- Arduino IDE (C++)
- Swagger para documentação

## Configuração do Backend

### Instalação das Dependências
```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows

#Instalar dependências
pip install Flask Flask-SQLAlchemy PyMySQL flasgger
```
### Configuração do Banco de Dados

O sistema utiliza MySQL.
1. Abra o MySQL Workbench (ou seu cliente de banco de dados preferido).
2. Crie um novo banco de dados (schema) para o projeto:
```bash
  CREATE DATABASE api_db;
```
3. No arquivo api.py, edite a linha SQLALCHEMY_DATABASE_URI com suas credenciais do MySQL:
```bash
# Exemplo de configuração: (usuário: 'root', senha: 'exemplo', banco: 'minha_api_db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:.de1ate5@localhost:3306/minha_api_db'
```
### Executando a API

Depois de configurar o banco, rode o servidor Flask:
```bash
python api_ponto_v4_local_time.py
```
- A API começará a rodar em host='0.0.0.0', o que a torna acessível pela sua rede local.
- Na primeira vez que rodar, o db.create_all() criará automaticamente as tabelas usuario e registro_ponto no seu banco.
# IMPORTANTE: Configuração do Firewall

Para que o ESP8266 (que está na sua rede) possa se conectar à sua API (que está no seu PC), você precisa criar uma regra no firewall do seu sistema operacional (Windows, Linux ou Mac) para permitir conexões de entrada na porta TCP 5000.

## - No Windows:

1. Abra "Firewall do Windows Defender com Segurança Avançada".
2. Vá em "Regras de Entrada" -> "Nova Regra...".
3. Selecione "Porta" -> "TCP" -> "Portas locais específicas:" -> 5000.
4. Selecione "Permitir a conexão" e marque os perfis (Domínio, Particular, Público).
5. Dê um nome à regra (ex: API Ponto Flask).

# Configuração do Hardware (ESP8266)

O firmware do ESP8266 (NFC_v2.ino ou NFC_v3_Feedback.ino) é responsável por ler o cartão e se comunicar com a API.

### Bibliotecas da IDE do Arduino
Abra a IDE do Arduino e, em Ferramentas > Gerenciar Bibliotecas..., instale:
1. Adafruit PN532 (e suas dependências, como Adafruit BusIO)
2. ArduinoJson (por Benoit Blanchon)
3. Verifique se você tem o pacote de placas esp8266 instalado em Ferramentas > Placa > Gerenciador de Placas.

|Pino do Leitor PN532           |Pino na Placa (LoLin NodeMCU)|
|-------------------------------|-----------------------------|
|`SCL`                          |`D1`                         |
|`SDA`                          |`D2`                         |
|`VCC`                          |`3.3`                        |
|`GND`                          |`GND`                        |

Configuração do Firmware

Abra o arquivo `.ino` e atualize as seguintes variáveis no topo do código:
````bash
// 1. Configurações da sua rede WiFi
const char* ssid = "NOME_DA_SUA_REDE_WIFI";
const char* password = "SENHA_DA_SUA_REDE_WIFI";

// 2. IP do computador que está rodando a API
const char* serverAddress = "IP_DO_PC_COM_A_API"; // Ex: "10.241.0.25"
````

## Carregando o Código

1. Em ``Ferramentas > Placa``, selecione "NodeMCU 1.0 (ESP-12E Module)".
2. Em ``Ferramentas > Porta``, selecione a porta COM correta.
3. Clique em "Carregar" (Upload).

# Como Usar o Sistema

**1. Documentação Interativa (Swagger)**

Com a API rodando, acesse a documentação no seu navegador. Esta é a forma mais fácil de testar as rotas e ver o que o sistema pode fazer:
``http://[IP_DO_SEU_PC]:5000/apidocs``

**2. Registrar um Novo Usuário**

Antes de usar o leitor, você precisa associar um cartão a um nome.

1. Aproxime o cartão que você quer registrar do leitor e abra o Monitor Serial (na IDE do Arduino) para ver o UID dele (ex: ``ID do Usuário (UID): DE284269``).
2. Vá até a página do Swagger (``/apidocs``).
3. Encontre a rota ``POST /registrar``, clique em "Try it out".
4. No corpo (body) da requisição, insira o UID e o nome:
````bash
{
  "card_uid": "DE284269",
  "nome": "Seu Nome Aqui"
}
````

5. Clique em "Execute". O usuário agora está cadastrado.

**3. Bater o Ponto**

Simplesmente aproxime um cartão cadastrado do leitor. O Monitor Serial da IDE do Arduino mostrará a resposta da API (ex: "SUCESSO: Entrada registrada!" ou "SUCESSO: Saída registrada!").

**4. Consultar Horas Totais**

Na interface do Swagger, use a rota ``GET /ponto/total/{card_uid}``.
1. Clique em "Try it out".
2. Digite o ``card_uid`` do usuário que você quer consultar (ex: ``DE284269``).
3. Clique em "Execute".
A API retornará um JSON completo com o total de horas trabalhadas por aquele usuário, já calculado para o dia, semana, mês e o total acumulado (com base no fuso horário UTC-3 definido na API).
