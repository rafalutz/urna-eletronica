# 🗳️ Sistema de Urna Eletrônica e Apuração (TRE Simulado)

Projeto desenvolvido com **Python**, **Tkinter** e **Flask**, simulando o processo eleitoral brasileiro com foco em **segurança**, **sigilo do voto (RDV)** e **apuração em tempo real**.

---

## 🔒 1. Como o Sigilo do Voto foi Implementado

Em conformidade com a Constituição Federal (Art. 14 — *o voto é direto e secreto*):

1. **Desvinculação Total**: O arquivo `votos.json` armazena **apenas** as opções de voto (`numero_cand`, `nome_cand`, `partido_cand`). Em nenhum momento o CPF, nome ou qualquer dado do eleitor é gravado junto ao voto.
2. **Folha de Presença Separada**: O arquivo `eleitores_votados.json` registra apenas quem compareceu à seção eleitoral para impedir duplicidade de voto. Não há nenhuma chave estrangeira, ID ou vínculo entre as duas tabelas.
3. **Embaralhamento Aleatório (Registro Digital do Voto - RDV)**: Toda vez que um voto é confirmado, a lista completa de votos em `votos.json` é **reembaralhada aleatoriamente** (`random.shuffle`). Isso impossibilita a correlação por ordem de votação (ex: descobrir que o 1º eleitor da fila foi o 1º voto do arquivo).
4. **Sanitização Automática no Servidor**: O backend em Flask possui uma camada de sanitização que expurga preventivamente qualquer campo identificador caso surja em `votos.json`.

---

## 🚀 2. Como Executar

### Pré-requisitos
Instale as dependências com:
```bash
pip install flask
```

### Passo 1: Iniciar o Painel de Apuração (Flask)
No terminal, execute:
```bash
python app.py
```
Acesse no seu navegador:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

### Passo 2: Executar a Urna Eletrônica
Você pode abrir o notebook `urna.ipynb` no Jupyter Notebook / VS Code, ou rodar o script diretamente no terminal:
```bash
python urna.py
```

À medida que os eleitores votam na urna, a tela do Flask atualiza **automaticamente a cada 3 segundos** via API (`/api/apuracao`), sem necessidade de recarregar a página!

---

## 📊 3. Funcionalidades da Tela de Apuração

- **Atualização em Tempo Real (Live Polling)**: Painel atualiza dinamicamente a cada 3 segundos.
- **Gráfico Interativo de Rosca**: Distribuição dos votos em tempo real via Chart.js.
- **Cards de Indicadores (KPIs)**: Total de votos apurados, eleitores que compareceram, candidato líder e percentual.
- **Ranking Visual de Candidatos**: Barras de progresso com as cores de cada partido, foto/emoji, números e status.
- **Boletim de Urna (BU)**: Página especial com layout de papel térmico oficial do TSE pronta para visualização e impressão em PDF (`/boletim`).
- **Zerésima**: Botão com confirmação para zerar a urna e iniciar uma nova rodada de testes do zero (`/api/zerar`).

---

## 📁 4. Estrutura de Arquivos

```text
urna/
├── api/
│   └── index.py             # Ponto de entrada Serverless para a Vercel
├── app.py                   # Servidor Flask (backend da apuração e API)
├── urna.py                  # Script Python da Urna Eletrônica (Tkinter)
├── urna.ipynb               # Notebook da Urna Eletrônica atualizado
├── eleitores_votados.json   # Lista de CPFs dos eleitores que já votaram (presença)
├── votos.json               # Votos anônimos e embaralhados (RDV sigiloso)
├── templates/
│   ├── apuracao.html        # Interface moderna da apuração em tempo real
│   └── boletim.html         # Boletim de Urna oficial para impressão
├── vercel.json              # Regras de reescrita de rotas para a Vercel
├── requirements.txt         # Dependências Python para a Vercel
├── .gitignore               # Arquivos ignorados pelo Git
└── README.md                # Esta documentação
```

---

## ☁️ 5. Deploy na Vercel

O painel de apuração e o Boletim de Urna estão preparados para deploy direto na **Vercel**:
1. Conecte o repositório GitHub à sua conta na [Vercel](https://vercel.com).
2. A Vercel detectará o arquivo `requirements.txt` e `api/index.py` automaticamente.
3. Clique em **Deploy**. A apuração e o boletim estarão disponíveis no seu domínio `.vercel.app`.
