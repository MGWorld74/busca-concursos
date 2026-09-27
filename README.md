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
├── firebase-messaging-sw.js          # service worker dos avisos push (precisa ficar na raiz)
├── concursos.json                    # gerado/atualizado automaticamente — não editar à mão
├── notificados.json                  # controle interno de avisos já enviados — não editar à mão
├── robots.txt
├── LICENSE
├── scripts/
│   └── atualizar_concursos.py        # scraper que roda no GitHub Actions
└── .github/workflows/
    └── atualizar.yml                 # agendamento (cron) + commit automático
```

## Avisos (notificações push)

O site pode avisar por notificação push — mesmo com o navegador fechado —
quando sair um concurso novo compatível com um âmbito (nacional/estadual/
municipal), UF, município e/ou cargo/termo escolhidos pela pessoa. Usa o
**Firebase Cloud Messaging** (gratuito, plano Spark) só para entregar a
notificação; nenhum dado pessoal é coletado, apenas um token de dispositivo
e os critérios do alerta.

Como funciona: ao ativar os avisos, o navegador gera um token de notificação
e a pessoa salva um "alerta" (critérios + token) direto no Cloud Firestore,
pelo próprio navegador. A cada execução (a cada 4h), o robô do GitHub Actions
compara os concursos novos com os alertas ativos e dispara as notificações
via Firebase Admin SDK.

### Configuração (uma vez, feita pelo dono do repositório)

1. Criar um projeto gratuito em [console.firebase.google.com](https://console.firebase.google.com).
2. Ativar **Cloud Firestore** (modo produção).
3. Em *Configurações do projeto → Cloud Messaging*, gerar o certificado
   push da Web (chave VAPID).
4. Registrar um app da Web no projeto e copiar o `firebaseConfig` — é
   público por natureza, seguro para deixar no código do site.
5. Em Firestore → Regras, usar:
   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /alertas/{alertaId} {
         allow create: if request.resource.data.keys().hasAll(['ambito','termo','uf','municipio','token','criadoEm','ativo'])
                       && request.resource.data.token is string
                       && request.resource.data.ativo == true;
         allow update: if resource.data.ativo == true
                       && request.resource.data.diff(resource.data).affectedKeys().hasOnly(['ativo'])
                       && request.resource.data.ativo == false;
         allow read, delete: if false;
       }
     }
   }
   ```
   Isso permite que qualquer visitante crie ou desative o próprio alerta,
   mas ninguém consegue ler ou apagar os alertas de outra pessoa.
6. Gerar uma **conta de serviço** (Configurações do projeto → Contas de
   serviço → Gerar nova chave privada) e salvar o conteúdo do `.json`
   baixado como secret do repositório, em *Settings → Secrets and
   variables → Actions*, com o nome **`FIREBASE_SERVICE_ACCOUNT`**.
7. Colar o `firebaseConfig` e a chave VAPID em `index.html` e em
   `firebase-messaging-sw.js` (os dois arquivos precisam ter os mesmos
   valores).

`notificados.json` guarda, por um tempo, quais itens já geraram aviso, para
o robô não notificar a mesma pessoa duas vezes pelo mesmo concurso.

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

## Links de edital, órgão e banca

Cada card de concurso já vem com três atalhos, além do link da notícia:
- 🔍 **Buscar edital oficial** — pesquisa pronta no Google pelo nome do órgão + "edital".
- 🏛️ **Site do órgão** — pesquisa pronta pelo site oficial do órgão.
- 🏫 **Banca organizadora** — se o nome da banca aparece no título (lista própria
  com ~20 bancas comuns: Cebraspe, FGV, FCC, Vunesp, IBFC, IDECAN, AOCP, Quadrix
  etc.), linka direto pro site oficial da banca; senão, cai numa busca.

São links de busca (não um link direto garantido pro PDF do edital), porque a
única fonte de dados é o Google Notícias — que não traz esse link — mas abrem
exatamente o que a pessoa precisa em 1 clique, sem deixar o robô mais lento.

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
