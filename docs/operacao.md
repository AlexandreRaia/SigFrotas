# Operação: implantação, backup e restauração

Para quem administra o servidor (VPS Hostinger). Em desenvolvimento nada disto é usado: veja o `README.md`.

> **Aviso de teste:** os scripts de backup e restauração foram testados no PostgreSQL local (com criptografia, frase errada e restauração com donos e permissões). Os arquivos `Dockerfile`, `docker-compose.yml` e `deploy/Caddyfile` ainda **não foram executados**, porque não há Docker na máquina de desenvolvimento. Faça a primeira implantação num ambiente de teste e siga este roteiro antes de colocar usuários.

## 1. O que sobe na VPS

| Serviço | Função |
|---|---|
| `db` | PostgreSQL 16. Na primeira vez cria as roles (dona e aplicação) e o banco |
| `web` | O site (gunicorn). Aplica as migrações ao iniciar |
| `caddy` | Recebe o tráfego, obtém e renova o certificado HTTPS sozinho |
| `backup` | Só roda sob demanda (`docker compose run --rm backup`) |

O site conecta ao banco com a role **da aplicação** (sem privilégios de dono), para a RLS valer. As migrações usam a role **dona**.

## 2. Primeira implantação

Requisitos: VPS Linux com Docker e o plugin Docker Compose; um domínio com o DNS apontando para o IP da VPS; portas 80 e 443 abertas.

1. Firewall: liberar só SSH, 80 e 443 (`ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable`). Acesso por chave SSH, sem login de root por senha.
2. Clonar o repositório: `git clone https://github.com/AlexandreRaia/SigFrotas.git && cd SigFrotas`.
3. Criar o `.env`: `cp .env.example .env && chmod 600 .env` e preencher:
   - `DJANGO_SECRET_KEY`: gerar com `python3 -c "import secrets; print(secrets.token_urlsafe(60))"`.
   - `DOMINIO`: o domínio do sistema.
   - `PG_ADMIN_PASSWORD`, `DB_OWNER_PASSWORD`, `DB_APP_PASSWORD`: três senhas fortes e **diferentes**.
   - `BACKUP_PASSPHRASE`: frase longa que criptografa os backups. **Guarde uma cópia fora do servidor**: sem ela os backups não abrem.
   - `MUNICIPIO_PADRAO_SLUG`: o slug da prefeitura, para o login não pedir o campo "Prefeitura".
   - Deixe `DJANGO_DEBUG` e `DJANGO_ALLOWED_HOSTS` como estão: o compose força `False` e usa o `DOMINIO`.
4. Subir: `docker compose up -d --build`. Acompanhar: `docker compose logs -f web`.
5. Criar a prefeitura e o administrador (a senha é pedida no terminal):
   ```
   docker compose exec web python manage.py criar_municipio --nome "Prefeitura de ..." --slug meu-slug --uf SP --cnpj 00000000000000
   docker compose exec -it web python manage.py criar_admin --prefeitura meu-slug --nome "Nome" --email pessoa@exemplo.gov.br
   ```
6. Abrir `https://<dominio>/` e entrar. O certificado leva alguns instantes na primeira vez.
7. Configurar o backup diário (seção 3) e **fazer o primeiro teste de restauração** (seção 4).

Atualizar o sistema: `git pull && docker compose up -d --build` (as migrações rodam sozinhas).

## 2.1 E-mail das notificações

Avisos de chamado, orçamento, saldo baixo etc. também saem por e-mail. O serviço `notificacoes` do compose roda `enviar_notificacoes` a cada minuto. Para ligar o envio de verdade, preencha no `.env` os dados do serviço de e-mail da prefeitura (`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`) e o endereço do sistema em `SITE_URL` (vira o link nos e-mails). Enquanto o backend for o padrão (`console`), os e-mails só aparecem no log: `docker compose logs notificacoes`. Os avisos dentro do sistema (sino) funcionam sempre. Para ver e-mails que falharam: tabela `notificacoes` com `status = 'ERRO'`.

## 3. Backup diário

O script `scripts/backup.sh` faz o dump do banco (formato custom), confere que o arquivo abre, criptografa com AES-256 e apaga os arquivos mais antigos que `RETENCAO_DIAS`. Se existirem anexos, empacota e criptografa também. Os arquivos ficam em `./backups/`.

Agendar no servidor (`crontab -e`, todo dia às 02:00):

```
0 2 * * * cd /caminho/SigFrotas && docker compose run --rm backup >> backups/backup.log 2>&1
```

**Cópia fora do servidor (obrigatória na prática):** backup guardado só na mesma VPS se perde junto com ela. Copie `./backups/` para outro lugar todo dia (por exemplo `rclone`, `rsync` ou `scp` para outro servidor ou armazenamento). Os arquivos já saem criptografados.

Metas sugeridas (a confirmar com a chefia): perder no máximo 24 horas de dados e voltar ao ar em algumas horas.

## 4. Teste de restauração (mensal, e sempre depois de mudar o servidor)

Backup que nunca foi restaurado não é backup. O teste restaura o arquivo mais recente num banco **temporário**, confere se as migrações, as tabelas e as políticas de RLS vieram e apaga o temporário. Não toca no banco de verdade.

```
docker compose run --rm backup /scripts/restaurar_teste.sh
```

O resultado esperado termina em `RESTAURACAO OK`. Se terminar em `RESTAURACAO COM FALHAS` ou der erro (por exemplo `bad decrypt`, frase errada), trate como incidente: o backup não está servindo. Anote a data e o resultado do teste.

## 5. Restauração real (desastre)

Isto **apaga o banco atual** e o recria do backup. Use só quando necessário e depois de um teste de restauração bem-sucedido do mesmo arquivo.

```
docker compose stop web caddy
docker compose run --rm backup /scripts/restaurar.sh --confirmo /backups/sigfrotas_AAAAMMDD_HHMMSS.dump.enc [/backups/anexos_AAAAMMDD_HHMMSS.tar.gz.enc]
docker compose start web caddy
```

Se a VPS foi perdida: instale o Docker, clone o repositório, recrie o `.env` (com a **mesma** `BACKUP_PASSPHRASE`), rode `docker compose up -d db`, copie os arquivos de backup para `./backups/` e siga o comando acima.

## 6. Dia a dia

- Logs: `docker compose logs --tail 100 web` (e `caddy`, `db`).
- Reiniciar o site: `docker compose restart web`.
- Espaço em disco: acompanhar `./backups/` e o volume do banco (`docker system df`).
- Segurança: manter o sistema operacional atualizado; nunca versionar o `.env`; trocar as senhas se houver suspeita de vazamento.
