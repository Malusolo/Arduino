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
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows
pip install Flask Flask-SQLAlchemy PyMySQL flasgger
