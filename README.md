# Sistema de Avaliação de Candidatos por Juízes 🏆

Aplicação web completa, funcional, responsiva e segura para avaliação, consolidação de notas e classificação de candidatos em eventos, concursos, festivais e bancas examinadoras.

---

## 📌 Sumário
- [Visão Geral](#visão-geral)
- [Perfis de Usuário](#perfis-de-usuário)
- [Regras de Negócio e Cálculo da Classificação](#regras-de-negócio-e-cálculo-da-classificação)
- [Arquitetura e Segurança](#arquitetura-e-segurança)
- [Instalação e Execução](#instalação-e-execução)
- [Credenciais Padrão de Demonstração](#credenciais-padrão-de-demonstração)
- [Configuração de Novos Administradores e Juízes (CLI)](#configuração-de-novos-administradores-e-juízes-cli)
- [Suíte de Testes Automatizados](#suíte-de-testes-automatizados)
- [Guia de Deploy em Produção](#guia-de-deploy-em-produção)

---

## 🎯 Visão Geral

O sistema foi desenvolvido para oferecer uma experiência extremamente rápida, moderna e intuitiva tanto para os juízes (otimizada para smartphones e tablets durante a avaliação ao vivo) quanto para o comitê organizador (painel administrativo robusto com métricas em tempo real, governança e auditoria).

### Principais Destaques:
- **Zero Dependências Externas**: Utiliza a robusta biblioteca padrão do Python 3 (`wsgiref`, `sqlite3`, `hashlib`, `hmac`), garantindo portabilidade imediata em qualquer ambiente Linux/macOS/Windows sem conflitos de `pip` ou pacotes externos.
- **Single Page Application (SPA) Moderna**: Interface responsiva com botões táteis numéricos de 1 a 10 para os juízes, atualizações instantâneas de progresso e modais interativos.
- **Governança do Evento**: O administrador controla o ciclo de vida da votação (Aberta, Pausada ou Encerrada), permissão de correção de notas e publicação do resultado oficial.
- **Banco de Dados Persistente**: SQLite com modo WAL (`Write-Ahead Logging`) e integridade referencial ativada (`PRAGMA foreign_keys = ON;`).

---

## 👥 Perfis de Usuário

1. **Administrador**
   - Acesso irrestrito a todas as funcionalidades do sistema.
   - CRUD completo de Candidatos (com número de inscrição e descrição).
   - CRUD completo de Juízes (criação de credenciais de login).
   - CRUD individual de Categorias de Avaliação (criação, edição, ordenação e desativação segura).
   - Painel com KPIs em tempo real (total de candidatos, juízes, categorias, submissões pendentes e concluídas, percentual de conclusão).
   - Monitoramento individual do progresso de cada juiz e matriz detalhada de notas.
   - Consulta e homologação da classificação geral e do vencedor.
   - Controle do evento (abrir/encerrar votação, permitir/bloquear alterações de notas, divulgar resultado).

2. **Juiz**
   - Acesso por login e senha individuais.
   - Visualização estrita da sua bancada de votação (sem acesso ao painel admin, notas de terceiros ou resultados parciais).
   - Lista de candidatos disponíveis com filtros rápidos: "Todos", "Pendentes" e "Avaliados".
   - Interface ergonômica de atribuição de notas de 1 a 10 para cada categoria ativa.
   - Barra de progresso individual informando quantos candidatos foram avaliados e quantos restam.
   - Bloqueio automático de alterações após o encerramento da votação.

3. **Candidato**
   - Cadastrado no sistema com nome, número de inscrição e descrição.
   - **Sem acesso à plataforma**: não possui login, não acessa notas nem relatórios.

---

## 📐 Regras de Negócio e Cálculo da Classificação

### 1. Categorias de Avaliação Dinâmicas
- O administrador cadastra as categorias individualmente direto pelo painel web (ex: *Criatividade*, *Figurino*, *Apresentação*).
- O sistema permite adicionar, editar, ativar, desativar e excluir categorias.
- **Integridade Referencial Protegida**: se uma categoria já tiver votos registrados, o sistema desativa a categoria (soft delete) para proteger o histórico dos cálculos.

### 2. Validação Rigorosa das Avaliações
- Cada juiz avalia cada candidato atribuindo notas **inteiras de 1 a 10** em todas as categorias ativas.
- Avaliações incompletas são rejeitadas: todas as categorias ativas devem receber nota para a submissão ser confirmada.
- Unicidade garantida por constraint no banco de dados: `UNIQUE(judge_id, candidate_id, category_id)`. Não há duplicidade de registros.
- Caso o administrador configure a opção de permitir correção de notas antes do encerramento, o juiz pode atualizar suas avaliações; caso contrário, as notas submetidas tornam-se imutáveis.
- Após o status ser alterado para `CLOSED` (Encerrada), nenhuma nota pode ser inserida ou alterada.

### 3. Fórmula de Média e Classificação
Para cada candidato, o sistema soma todas as notas válidas atribuídas por juízes ativos em categorias ativas e divide pela quantidade total de notas válidas:

$$\text{Média Final} = \frac{\sum \text{Notas Válidas}}{\text{Quantidade Total de Notas Válidas}}$$

- **Exemplo**: se houver 3 categorias e 5 juízes, cada candidato acumulará até 15 notas. A média final será a soma das 15 notas dividida por 15.
- As médias são calculadas no backend e formatadas com **duas casas decimais** (ex: `9.85`).
- Os candidatos são ordenados da maior para a menor média final.
- **Tratamento de Empates**: se dois ou mais candidatos apresentarem a mesma média final, eles compartilham a mesma colocação (ex: ambos em 1º lugar com badge de *Empate*), sem escolhas arbitrárias pelo sistema.
- **Vencedor**: o candidato (ou candidatos, em caso de empate) no 1º lugar é destacado como *Vencedor Provisório* durante a apuração e como *Vencedor Oficial* após o encerramento da votação e homologação pelo administrador.

---

## 🔒 Arquitetura e Segurança

- **RBAC (Role-Based Access Control)**: Middleware backend verifica se o perfil do usuário autenticado tem permissão para a rota solicitada. Tentativas de acesso a rotas administrativas por juízes retornam `403 Forbidden`.
- **Criptografia de Senhas**: Utiliza `PBKDF2-HMAC-SHA256` com salt criptográfico aleatório (`secrets.token_hex(16)`) e 100.000 iterações.
- **Tokens de Autenticação**: Implementação nativa de tokens assinados com `HMAC-SHA256` (padrão JWT HS256) com validação de expiração e proteção contra timing attacks via `hmac.compare_digest`.
- **Auditoria**: Todas as ações críticas (login, cadastro de candidatos/juízes, alteração de configurações e encerramento de votação) são registradas na tabela `audit_logs`.

---

## 🚀 Instalação e Execução

### Pré-requisitos
- Python 3.8 ou superior (já pré-instalado na grande maioria dos sistemas operacionais).

### 1. Entrar na pasta do projeto
```bash
cd /Users/erasmorodrigues/.gemini/antigravity/scratch/sistema-avaliacao-juizes
```

### 2. Iniciar o Servidor Web
Execute diretamente:
```bash
python3 server.py
```
ou utilizando o utilitário CLI:
```bash
python3 manage.py runserver 8000
```

Abra o seu navegador em: **`http://localhost:8000`**

Ao iniciar pela primeira vez, o sistema cria o banco SQLite `sistema_avaliacao.db` e popula os dados padrão automaticamente.

---

## 🔑 Credenciais Padrão de Demonstração

| Perfil | Nome | E-mail | Senha |
|---|---|---|---|
| **Administrador** | Administrador Geral | `admin@sistema.com` | `admin123` |
| **Juíza** | Dra. Helena Martins | `helena@sistema.com` | `juiz123` |
| **Juiz** | Prof. Carlos Eduardo | `carlos@sistema.com` | `juiz123` |
| **Juíza** | Dra. Beatriz Albuquerque | `beatriz@sistema.com` | `juiz123` |

> Na tela de login há botões de **Acesso Rápido** que preenchem as credenciais com um único clique para facilitar os testes.

---

## 🛠️ Configuração de Novos Administradores e Juízes (CLI)

O arquivo `manage.py` oferece comandos práticos de linha de comando:

### Cadastrar ou redefinir Administrador:
```bash
python3 manage.py createadmin "admin@meuevento.com" "Nome do Administrador" "MinhaSenhaForte"
```

### Cadastrar novo Juiz:
```bash
python3 manage.py createjudge "juiz@meuevento.com" "Nome do Juiz" "SenhaJuiz123"
```

### Reinicializar Banco de Dados com Dados Padrão:
```bash
python3 manage.py resetdb
```

---

## 🧪 Suíte de Testes Automatizados

O sistema conta com 15 testes automatizados cobrindo todos os requisitos solicitados:

1. **Isolamento de Acesso (RBAC)**: Juiz recebe `403 Forbidden` ao acessar endpoints administrativos.
2. **Rejeição de Notas Inválidas**: Notas < 1, > 10, negativas ou não inteiras são rejeitadas com `400 Bad Request`.
3. **Prevenção de Duplicidade**: Mesmo juiz, candidato e categoria não gera múltiplos registros (atualiza sem duplicar).
4. **Bloqueio de Correção**: Juiz não consegue alterar nota quando a configuração está desativada.
5. **Bloqueio após Encerramento**: Notas são rejeitadas quando o status da votação é `CLOSED`.
6. **Cálculo da Média Geral**: Validação exata da fórmula matemática ($\text{soma} / \text{total}$) com duas casas decimais.
7. **Detecção de Empates**: Dois candidatos com a mesma média compartilham o mesmo rank e ativam flag de empate.
8. **Integridade de Categorias**: Exclusão segura de categorias com notas prévias via desativação (soft delete).
9. **Persistência do SQLite**: Dados continuam intactos após fechar e reabrir conexões de banco de dados.
10. **Rejeição de Avaliações Incompletas**: Juiz não consegue confirmar se faltar alguma categoria ativa.
11. **Fluxo de Login**: Validação de credenciais válidas e inválidas.
12. **Divulgação Pública**: Resultados públicos bloqueados até autorização do administrador.
13. **CRUD de Candidatos**: Criação, edição e exclusão de participantes.
14. **CRUD de Juízes**: Criação, edição e exclusão de juízes.
15. **Acesso do Administrador**: Verificação das rotas de gestão.

### Para rodar os testes:
```bash
python3 manage.py test
```

---

## 🌐 Guia de Deploy em Produção

Como a aplicação implementa o padrão WSGI (`app.wsgi:application`), ela pode ser executada em produção de diversas maneiras:

### Opção 1: Gunicorn (Recomendado para Linux)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app.wsgi:application
```

### Opção 2: Systemd Service (Linux Ubuntu/Debian)
Crie o arquivo `/etc/systemd/system/avaliacao.service`:
```ini
[Unit]
Description=Sistema de Avaliacao de Candidatos
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/sistema-avaliacao-juizes
Environment="DATABASE_PATH=/var/www/sistema-avaliacao-juizes/sistema_avaliacao.db"
Environment="APP_SECRET_KEY=sua-chave-secreta-de-producao-altamente-segura"
ExecStart=/usr/bin/python3 server.py
Restart=always

[Install]
WantedBy=multi-user.target
```
Habilite e inicie o serviço:
```bash
sudo systemctl daemon-reload
sudo systemctl enable avaliacao
sudo systemctl start avaliacao
```

### Opção 3: Nginx como Reverse Proxy com HTTPS
Configuração recomendada do Nginx:
```nginx
server {
    listen 80;
    server_name avaliacao.seudominio.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name avaliacao.seudominio.com;

    ssl_certificate /etc/letsencrypt/live/avaliacao.seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/avaliacao.seudominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

Desenvolvido para máxima confiabilidade, agilidade na votação e transparência na apuração.
