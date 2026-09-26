# Busca Concursos

Site estático de busca automática de concursos públicos no Brasil, organizado
por **âmbito** (Nacional, Estadual ou Municipal), com editais classificados em
**Edital Aberto**, **Edital Previsto** e notícias relacionadas.

100% gratuito para operar: GitHub Pages (hospedagem) + GitHub Actions
(robô de coleta agendado, minutos ilimitados em repositório público) + API
pública do IBGE. Sem servidor próprio, sem banco de dados, sem chaves de API.

## Como funciona

```
GitHub Actions (cron, a cada 4h)
        │
        ▼
scripts/atualizar_concursos.py   ← consulta Google Notícias diretamente (sem CORS,
        │                           pois roda no servidor do GitHub, não no navegador)
        ▼
concursos.json                   ← commit automático no repositório
        │
        ▼
GitHub Pages (index.html + concursos.json no mesmo domínio)
        │
        ▼
Navegador do usuário
  ├─ carrega concursos.json na abertura (rápido, sempre disponível)
  └─ complementa com busca ao vivo (Google Notícias via proxies CORS
     públicos, já que o navegador não pode chamar news.google.com direto)
```

Isso dá duas camadas de dados: uma **base confiável, atualizada de tempos em
tempos**, que funciona mesmo se os proxies CORS públicos falharem no
navegador de alguém; e uma **busca ao vivo**, mais imediata, que refina por
termos/órgão/cargo digitados na hora.

## Estrutura do repositório

```
├── index.html                        # o site (HTML + CSS + JS em arquivo único)
├── concursos.json                    # gerado/atualizado automaticamente — não editar à mão
├── robots.txt
├── LICENSE
├── scripts/
│   └── atualizar_concursos.py        # scraper que roda no GitHub Actions
└── .github/workflows/
    └── atualizar.yml                 # agendamento (cron) + commit automático
```

## Colocando no ar (passo a passo)

1. Crie um repositório **público** no GitHub (precisa ser público para ter
   minutos ilimitados de Actions de graça) e suba estes arquivos na raiz.
2. Em **Settings → Pages**, escolha "Deploy from a branch", branch `main`,
   pasta `/ (root)`. Depois de alguns minutos o site fica em
   `https://SEU-USUARIO.github.io/SEU-REPO/`.
3. Em **Settings → Actions → General → Workflow permissions**, marque
   "Read and write permissions" (necessário para o robô conseguir commitar
   o `concursos.json` sozinho).
4. Pronto. O workflow já roda sozinho a cada 4h. Para forçar uma primeira
   atualização sem esperar, vá em **Actions → Atualizar concursos → Run workflow**.

Não é necessário configurar nenhum segredo/API key — tudo usa endpoints
públicos (Google Notícias via RSS e a API de localidades do IBGE).

## Testando o scraper localmente (opcional)

```bash
pip install requests
python scripts/atualizar_concursos.py
```
Isso sobrescreve o `concursos.json` local com dados frescos, para conferir
antes de commitar.

## Limitações conhecidas (heurísticas, não garantias)

- A classificação de tipo (Abertura/Previsto/Alteração/Resultado), âmbito
  (nacional/estadual/municipal), UF, órgão, vagas e salário é feita por
  expressões regulares sobre o título da notícia — não há leitura do edital
  em si. Pode errar em títulos fora do padrão comum.
- A cobertura por município na base automática (`concursos.json`) é parcial:
  o robô roda consultas nacionais e por estado, não uma consulta para cada um
  dos ~5.570 municípios a cada execução (isso extrapolaria o razoável em
  requisições ao Google Notícias). A busca **ao vivo** por um município
  específico, feita pelo navegador quando o usuário seleciona um município,
  cobre esse caso sob demanda.
- Os proxies CORS públicos usados pela busca ao vivo no navegador (allorigins,
  corsproxy.io etc.) são de terceiros e podem cair ou mudar sem aviso — por
  isso a base automática existe, como camada de resiliência.

## Privacidade

Nada é enviado a um servidor próprio. Favoritos e preferências ficam apenas
no `localStorage` do navegador de cada pessoa.

## Ideias para evoluir (roadmap)

- [ ] Feed RSS próprio dos resultados (gerado junto com o `concursos.json`).
- [ ] Monitoramento de uptime gratuito (ex.: UptimeRobot) apontando para o site.
- [ ] Analytics sem cookies (ex.: Cloudflare Web Analytics ou GoatCounter).
- [ ] Amostragem periódica revisada manualmente para calibrar as regex de
      classificação.
- [ ] Rotacionar/priorizar municípios mais buscados (via analytics) para
      entrarem nas consultas automáticas do robô.

## Licença

MIT — veja [LICENSE](LICENSE).
