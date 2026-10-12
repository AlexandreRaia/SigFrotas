-- =====================================================================
-- Sistema de Gestao de Frotas - schema v2 (PostgreSQL 14+)
-- Multi-prefeitura: coluna municipio_id em todas as tabelas + RLS.
-- Na aplicacao: SET app.municipio_id = '<id>' a cada requisicao/transacao.
-- Este arquivo e a REFERENCIA do modelo. Na pratica o schema evolui por
-- migracoes do Django (nao rodar este arquivo em producao).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS frota;
SET search_path = frota, public;

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- evita conflito de agenda (veiculo/motorista)

CREATE OR REPLACE FUNCTION frota.municipio_atual() RETURNS bigint
LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.municipio_id', true), '')::bigint $$;

CREATE OR REPLACE FUNCTION frota.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS
$$ BEGIN NEW.atualizado_em = now(); RETURN NEW; END $$;

-- =====================================================================
-- 1. NUCLEO: PREFEITURA, ESTRUTURA ORGANIZACIONAL, ACESSO
-- =====================================================================
CREATE TABLE municipios (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome          text NOT NULL,
    uf            varchar(2) NOT NULL,
    cnpj          varchar(14) NOT NULL UNIQUE,
    codigo_ibge   varchar(7),
    config        jsonb NOT NULL DEFAULT '{}',     -- parametros da prefeitura (prazos, regras, textos)
    ativo         boolean NOT NULL DEFAULT true,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE secretarias (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    sigla         varchar(20) NOT NULL,
    nome          text NOT NULL,
    ativo         boolean NOT NULL DEFAULT true,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, sigla)
);

CREATE TABLE unidades (                             -- divisoes dentro da secretaria
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    secretaria_id bigint NOT NULL REFERENCES secretarias(id),
    nome          text NOT NULL,
    codigo_externo varchar(30),                     -- codigo da unidade/subunidade na Prime
    ativo         boolean NOT NULL DEFAULT true,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (secretaria_id, nome)
);

CREATE TABLE centros_custo (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    secretaria_id bigint REFERENCES secretarias(id),
    codigo        varchar(30) NOT NULL,
    nome          text NOT NULL,
    codigo_externo varchar(30),                     -- como o centro de custo aparece na Prime
    ativo         boolean NOT NULL DEFAULT true,
    UNIQUE (municipio_id, codigo)
);

CREATE TABLE perfis (                               -- ADMIN, GESTOR_FROTA, GESTOR_UNIDADE, SOLICITANTE, MOTORISTA, FISCAL, OFICINA, CONSULTA
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    codigo        varchar(30) NOT NULL,
    nome          varchar(60) NOT NULL,
    permissoes    jsonb NOT NULL DEFAULT '[]',
    UNIQUE (municipio_id, codigo)
);

CREATE TABLE usuarios (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    perfil_id     bigint NOT NULL REFERENCES perfis(id),
    secretaria_id bigint REFERENCES secretarias(id),
    unidade_id    bigint REFERENCES unidades(id),
    fornecedor_id bigint,                           -- preenchido para usuarios de oficina (FK em fornecedores, adicionada abaixo)
    nome          text NOT NULL,
    email         citext NOT NULL,
    cpf           varchar(11),
    matricula     varchar(20),
    senha_hash    text NOT NULL,
    ativo         boolean NOT NULL DEFAULT true,
    ultimo_login  timestamptz,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, email)
);

-- =====================================================================
-- 2. CATALOGOS
-- =====================================================================
CREATE TABLE marcas (
    id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome  text NOT NULL UNIQUE                      -- global
);

CREATE TABLE modelos (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    marca_id  bigint NOT NULL REFERENCES marcas(id),
    nome      text NOT NULL,
    UNIQUE (marca_id, nome)
);

CREATE TABLE combustiveis (
    id    smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome  varchar(30) NOT NULL UNIQUE               -- global
);

CREATE TABLE categorias_veiculo (                   -- automovel, caminhao, onibus, moto, maquina...
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    nome          varchar(60) NOT NULL,
    cnh_minima    varchar(5),
    usa_horimetro boolean NOT NULL DEFAULT false,   -- maquinas
    UNIQUE (municipio_id, nome)
);

CREATE TABLE categorias_servico (                   -- categoria do item de orcamento (freios, suspensao, eletrica...)
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    nome          varchar(60) NOT NULL,
    UNIQUE (municipio_id, nome)
);

-- =====================================================================
-- 3. FORNECEDORES, CONTRATOS, FISCAIS E EMPENHOS
-- =====================================================================
CREATE TABLE fornecedores (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    cnpj_cpf      varchar(14) NOT NULL,
    razao_social  text NOT NULL,
    tipo          varchar(20) NOT NULL CHECK (tipo IN ('OFICINA','LOCADORA','POSTO','AUTOPECAS','SEGURADORA','OPERADORA_CARTAO','OUTRO')),
    telefone      varchar(20),
    email         citext,
    ativo         boolean NOT NULL DEFAULT true,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, cnpj_cpf)
);

ALTER TABLE usuarios ADD CONSTRAINT fk_usuarios_fornecedor FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id);

CREATE TABLE contratos (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    fornecedor_id bigint NOT NULL REFERENCES fornecedores(id),
    tipo          varchar(20) NOT NULL CHECK (tipo IN ('MANUTENCAO','LOCACAO','COMBUSTIVEL','SEGURO','OUTRO')),
    numero        varchar(40) NOT NULL,
    processo      varchar(40),
    objeto        text NOT NULL,
    vigencia_ini  date NOT NULL,
    vigencia_fim  date NOT NULL,
    valor_total   numeric(14,2),
    ativo         boolean NOT NULL DEFAULT true,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, numero),
    CHECK (vigencia_fim >= vigencia_ini)
);

CREATE TABLE fiscais_contrato (                     -- quem fiscaliza qual contrato em qual centro de custo
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id    bigint NOT NULL REFERENCES municipios(id),
    contrato_id     bigint NOT NULL REFERENCES contratos(id),
    centro_custo_id bigint REFERENCES centros_custo(id),   -- nulo = todos
    usuario_id      bigint NOT NULL REFERENCES usuarios(id),
    suplente        boolean NOT NULL DEFAULT false,
    vigencia_ini    date NOT NULL DEFAULT current_date,
    vigencia_fim    date
);

CREATE TABLE empenhos (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id     bigint NOT NULL REFERENCES municipios(id),
    contrato_id      bigint NOT NULL REFERENCES contratos(id),
    centro_custo_id  bigint NOT NULL REFERENCES centros_custo(id),
    numero           varchar(30) NOT NULL,
    exercicio        smallint NOT NULL,
    valor_empenhado  numeric(14,2) NOT NULL,
    data_empenho     date,
    ativo            boolean NOT NULL DEFAULT true,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, exercicio, numero)
);

CREATE TABLE empenho_lancamentos (                  -- saldo = empenhado - reservas - consumos (+ estornos); ver vw_saldo_empenho
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    empenho_id    bigint NOT NULL REFERENCES empenhos(id),
    tipo          varchar(10) NOT NULL CHECK (tipo IN ('RESERVA','CONSUMO','ESTORNO')),
    valor         numeric(14,2) NOT NULL CHECK (valor > 0),
    orcamento_id  bigint,                           -- FK adicionada abaixo
    observacao    text,
    criado_por    bigint REFERENCES usuarios(id),
    criado_em     timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 4. VEICULOS
-- =====================================================================
CREATE TABLE veiculos (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id        bigint NOT NULL REFERENCES municipios(id),
    secretaria_id       bigint REFERENCES secretarias(id),
    unidade_id          bigint REFERENCES unidades(id),
    centro_custo_id     bigint REFERENCES centros_custo(id),
    categoria_id        bigint REFERENCES categorias_veiculo(id),
    modelo_id           bigint REFERENCES modelos(id),
    combustivel_id      smallint REFERENCES combustiveis(id),
    placa               varchar(8) NOT NULL,
    prefixo             varchar(20),
    patrimonio          varchar(30),
    renavam             varchar(11),
    chassi              varchar(17),
    ano_fabricacao      smallint,
    ano_modelo          smallint,
    cor                 varchar(30),
    motor               varchar(60),                    -- cilindrada/potencia
    transmissao         varchar(20),                    -- MANUAL, AUTOMATICA, CVT...
    capacidade_tanque   numeric(6,2),
    consumo_referencia  numeric(5,2),                   -- km/l esperado
    capacidade_passageiros smallint,
    odometro_atual      integer NOT NULL DEFAULT 0,
    horimetro_atual     numeric(10,1),
    km_entrada          integer,                        -- km ao entrar na frota
    estado_conservacao  varchar(10) CHECK (estado_conservacao IN ('BOM','REGULAR','RUIM','PESSIMO')),
    situacao            varchar(15) NOT NULL DEFAULT 'DISPONIVEL'
                        CHECK (situacao IN ('DISPONIVEL','EM_USO','MANUTENCAO','RESERVA','INATIVO','BAIXADO')),
    tipo_frota          varchar(10) NOT NULL DEFAULT 'PROPRIO'
                        CHECK (tipo_frota IN ('PROPRIO','LOCADO','ESTADUAL','DOACAO','CEDIDO')),
    proprietario        text,                           -- razao social da locadora/orgao
    contrato_locacao_id bigint REFERENCES contratos(id),
    valor_fipe          numeric(14,2),
    valor_aquisicao     numeric(14,2),
    valor_aluguel_mensal numeric(14,2),
    data_aquisicao      date,
    data_baixa          date,
    motivo_baixa        text,
    criado_em           timestamptz NOT NULL DEFAULT now(),
    atualizado_em       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, placa)
);

CREATE TABLE veiculo_equipamentos (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    veiculo_id    bigint NOT NULL REFERENCES veiculos(id) ON DELETE CASCADE,
    descricao     varchar(100) NOT NULL,                -- ar-condicionado, radio comunicador, roda liga leve...
    observacao    text
);

CREATE TABLE veiculo_lotacoes (                     -- historico de secretaria/unidade/centro de custo
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id    bigint NOT NULL REFERENCES municipios(id),
    veiculo_id      bigint NOT NULL REFERENCES veiculos(id),
    secretaria_id   bigint REFERENCES secretarias(id),
    unidade_id      bigint REFERENCES unidades(id),
    centro_custo_id bigint REFERENCES centros_custo(id),
    inicio          date NOT NULL,
    fim             date
);

CREATE TABLE leituras_veiculo (                     -- fonte unica de km/horimetro
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    veiculo_id    bigint NOT NULL REFERENCES veiculos(id),
    odometro      integer,
    horimetro     numeric(10,1),
    lido_em       timestamptz NOT NULL DEFAULT now(),
    origem        varchar(20) NOT NULL,                 -- FICHA, ABASTECIMENTO, SMV, CHECKLIST, MANUAL
    origem_id     bigint
);

-- =====================================================================
-- 5. MOTORISTAS
-- =====================================================================
CREATE TABLE motoristas (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id   bigint NOT NULL REFERENCES municipios(id),
    usuario_id     bigint REFERENCES usuarios(id),
    secretaria_id  bigint REFERENCES secretarias(id),
    unidade_id     bigint REFERENCES unidades(id),
    prontuario     varchar(20) NOT NULL,
    nome           text NOT NULL,
    cpf            varchar(11) NOT NULL,
    rg             varchar(20),
    rg_emissor     varchar(20),
    data_nascimento date,
    cargo          varchar(80),
    telefone       varchar(20),
    email          citext,
    endereco       text,
    cep            varchar(8),
    cnh_numero     varchar(11),
    cnh_categoria  varchar(5),
    cnh_emissao    date,
    cnh_validade   date,
    cnh_orgao      varchar(20),
    situacao       varchar(10) NOT NULL DEFAULT 'ATIVO' CHECK (situacao IN ('ATIVO','SUSPENSO','INATIVO')),
    criado_em      timestamptz NOT NULL DEFAULT now(),
    atualizado_em  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, prontuario),
    UNIQUE (municipio_id, cpf)
);

CREATE TABLE motorista_certificados (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    motorista_id  bigint NOT NULL REFERENCES motoristas(id),
    curso         text NOT NULL,
    instituicao   text,
    realizado_em  date,
    validade      date
);

CREATE TABLE motorista_penalidades (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    motorista_id  bigint NOT NULL REFERENCES motoristas(id),
    descricao     text NOT NULL,
    penalidade    text,
    aplicada_em   date
);

CREATE TABLE motorista_afastamentos (               -- ferias, folgas e licencas (sem detalhar o motivo)
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    motorista_id  bigint NOT NULL REFERENCES motoristas(id),
    tipo          varchar(10) NOT NULL CHECK (tipo IN ('FERIAS','FOLGA','LICENCA','OUTRO')),
    inicio        date NOT NULL,
    fim           date NOT NULL,
    CHECK (fim >= inicio)
);

-- =====================================================================
-- 6. SOLICITACAO E AGENDAMENTO DE VEICULOS
-- =====================================================================
CREATE TABLE solicitacoes_veiculo (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id       bigint NOT NULL REFERENCES municipios(id),
    numero             varchar(20) NOT NULL,
    solicitante_id     bigint NOT NULL REFERENCES usuarios(id),
    secretaria_id      bigint NOT NULL REFERENCES secretarias(id),
    unidade_id         bigint REFERENCES unidades(id),
    categoria_id       bigint REFERENCES categorias_veiculo(id),  -- tipo de veiculo desejado
    saida_prevista     timestamptz NOT NULL,
    retorno_previsto   timestamptz NOT NULL,
    origem             text,
    destino            text NOT NULL,
    passageiros        smallint,
    finalidade         text NOT NULL,
    prioridade         varchar(10) NOT NULL DEFAULT 'NORMAL' CHECK (prioridade IN ('BAIXA','NORMAL','ALTA','URGENTE')),
    status_aprovacao   varchar(10) NOT NULL DEFAULT 'PENDENTE'
                       CHECK (status_aprovacao IN ('PENDENTE','APROVADA','REPROVADA','CANCELADA')),
    status_andamento   varchar(12) NOT NULL DEFAULT 'PENDENTE'
                       CHECK (status_andamento IN ('PENDENTE','EM_ANDAMENTO','FINALIZADO')),
    veiculo_id         bigint REFERENCES veiculos(id),       -- definidos na aprovacao
    motorista_id       bigint REFERENCES motoristas(id),
    analisado_por      bigint REFERENCES usuarios(id),
    analisado_em       timestamptz,
    motivo_decisao     text,
    criado_em          timestamptz NOT NULL DEFAULT now(),
    atualizado_em      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, numero),
    CHECK (retorno_previsto > saida_prevista)
);
CREATE INDEX ON solicitacoes_veiculo (municipio_id, secretaria_id, saida_prevista);

-- impede, no proprio banco, dois agendamentos aprovados para o mesmo veiculo/motorista no mesmo periodo
ALTER TABLE solicitacoes_veiculo ADD CONSTRAINT ex_agenda_veiculo
    EXCLUDE USING gist (veiculo_id WITH =, tstzrange(saida_prevista, retorno_previsto) WITH &&)
    WHERE (status_aprovacao = 'APROVADA' AND veiculo_id IS NOT NULL);
ALTER TABLE solicitacoes_veiculo ADD CONSTRAINT ex_agenda_motorista
    EXCLUDE USING gist (motorista_id WITH =, tstzrange(saida_prevista, retorno_previsto) WITH &&)
    WHERE (status_aprovacao = 'APROVADA' AND motorista_id IS NOT NULL);

-- =====================================================================
-- 7. CONTROLE DE TRAFEGO DIGITAL (substitui a ficha de papel)
-- =====================================================================
CREATE TABLE fichas_trafego (                       -- uma ficha por motorista/veiculo/dia
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id       bigint NOT NULL REFERENCES municipios(id),
    client_uuid        uuid NOT NULL,                       -- gerado no celular; garante que o envio offline nao duplica
    veiculo_id         bigint NOT NULL REFERENCES veiculos(id),
    motorista_id       bigint NOT NULL REFERENCES motoristas(id),
    solicitacao_id     bigint REFERENCES solicitacoes_veiculo(id),
    secretaria_id      bigint REFERENCES secretarias(id),
    unidade_id         bigint REFERENCES unidades(id),
    data_ficha         date NOT NULL,
    departamento_requisitante text,
    plantao_inicio     time,
    plantao_fim        time,
    km_inicial         integer,
    km_final           integer,
    horimetro_inicial  numeric(10,1),
    horimetro_final    numeric(10,1),
    status             varchar(15) NOT NULL DEFAULT 'RASCUNHO'
                       CHECK (status IN ('RASCUNHO','ENVIADA','VALIDADA_GESTOR','DEVOLVIDA','CONFERIDA','ARQUIVADA')),
    origem_registro    varchar(10) NOT NULL DEFAULT 'APP' CHECK (origem_registro IN ('APP','WEB','PAPEL')),
    assinada_em        timestamptz,                         -- confirmacao do motorista
    enviada_em         timestamptz,
    sincronizada_em    timestamptz,
    validada_por       bigint REFERENCES usuarios(id),      -- gestor da unidade
    validada_em        timestamptz,
    conferida_por      bigint REFERENCES usuarios(id),      -- Departamento de Transportes
    conferida_em       timestamptz,
    motivo_devolucao   text,
    criado_em          timestamptz NOT NULL DEFAULT now(),
    atualizado_em      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, client_uuid),
    CHECK (km_final IS NULL OR km_inicial IS NULL OR km_final >= km_inicial)
);
CREATE INDEX ON fichas_trafego (municipio_id, status, data_ficha);
CREATE INDEX ON fichas_trafego (municipio_id, veiculo_id, data_ficha);

CREATE TABLE ficha_trechos (                        -- linhas da ficha: partida, itinerario, chegada
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    ficha_id      bigint NOT NULL REFERENCES fichas_trafego(id) ON DELETE CASCADE,
    sequencia     smallint NOT NULL,
    partida_em    timestamptz,
    km_partida    integer,
    itinerario    text,
    chegada_em    timestamptz,
    km_chegada    integer,
    usuario_nome  text,                                 -- passageiro/usuario atendido
    UNIQUE (ficha_id, sequencia),
    CHECK (km_chegada IS NULL OR km_partida IS NULL OR km_chegada >= km_partida)
);

CREATE TABLE ficha_pontos_gps (                     -- trilha do trajeto (alto volume: particionar por data no futuro)
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    ficha_id      bigint NOT NULL REFERENCES fichas_trafego(id) ON DELETE CASCADE,
    trecho_id     bigint REFERENCES ficha_trechos(id) ON DELETE CASCADE,
    capturado_em  timestamptz NOT NULL,
    latitude      numeric(9,6) NOT NULL,
    longitude     numeric(9,6) NOT NULL,
    precisao_m    numeric(7,1)
);
CREATE INDEX ON ficha_pontos_gps (ficha_id, capturado_em);

CREATE TABLE ficha_historico (                      -- quem enviou, validou, devolveu, conferiu
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    ficha_id      bigint NOT NULL REFERENCES fichas_trafego(id) ON DELETE CASCADE,
    acao          varchar(20) NOT NULL,
    usuario_id    bigint REFERENCES usuarios(id),
    observacao    text,
    em            timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 8. CHECKLISTS CONFIGURAVEIS (saida/retorno e vistoria de oficina)
-- =====================================================================
CREATE TABLE checklist_modelos (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    nome          varchar(80) NOT NULL,
    finalidade    varchar(15) NOT NULL CHECK (finalidade IN ('TRAFEGO','VISTORIA_OFICINA')),
    categoria_id  bigint REFERENCES categorias_veiculo(id),   -- nulo = todas
    ativo         boolean NOT NULL DEFAULT true
);

CREATE TABLE checklist_itens (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    modelo_id     bigint NOT NULL REFERENCES checklist_modelos(id) ON DELETE CASCADE,
    grupo         varchar(40) NOT NULL,                 -- Conservacao, Seguranca, Eletrica, Lubrificantes, Equipamentos
    descricao     varchar(120) NOT NULL,
    sequencia     smallint NOT NULL DEFAULT 0,
    critico       boolean NOT NULL DEFAULT false        -- item critico gera alerta imediato
);

CREATE TABLE checklist_execucoes (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id     bigint NOT NULL REFERENCES municipios(id),
    modelo_id        bigint NOT NULL REFERENCES checklist_modelos(id),
    veiculo_id       bigint NOT NULL REFERENCES veiculos(id),
    motorista_id     bigint REFERENCES motoristas(id),
    ficha_id         bigint REFERENCES fichas_trafego(id),
    smv_id           bigint,                                -- FK adicionada abaixo
    momento          varchar(15) NOT NULL CHECK (momento IN ('INICIO','FINAL','ENTRADA_OFICINA','ENTREGA_OFICINA')),
    executado_em     timestamptz NOT NULL DEFAULT now(),
    odometro         integer,
    nivel_combustivel varchar(4) CHECK (nivel_combustivel IN ('R','1/4','1/2','3/4','C')),
    tem_irregularidade boolean NOT NULL DEFAULT false
);

CREATE TABLE checklist_respostas (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    execucao_id   bigint NOT NULL REFERENCES checklist_execucoes(id) ON DELETE CASCADE,
    item_id       bigint NOT NULL REFERENCES checklist_itens(id),
    conforme      boolean NOT NULL,
    observacao    text
);

-- =====================================================================
-- 9. MANUTENCAO: CHAMADO -> SMV -> ORCAMENTO -> EXECUCAO -> NOTA FISCAL
-- =====================================================================
CREATE TABLE chamados (                             -- relato de defeito (motorista, fiscal, unidade, checklist)
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id     bigint NOT NULL REFERENCES municipios(id),
    numero           varchar(20) NOT NULL,
    veiculo_id       bigint NOT NULL REFERENCES veiculos(id),
    aberto_por       bigint NOT NULL REFERENCES usuarios(id),
    origem           varchar(12) NOT NULL DEFAULT 'MANUAL' CHECK (origem IN ('MANUAL','CHECKLIST','PREVENTIVA','FISCAL')),
    checklist_execucao_id bigint REFERENCES checklist_execucoes(id),
    descricao        text NOT NULL,
    prioridade       varchar(10) NOT NULL DEFAULT 'NORMAL' CHECK (prioridade IN ('BAIXA','NORMAL','ALTA','URGENTE')),
    status           varchar(15) NOT NULL DEFAULT 'ABERTO'
                     CHECK (status IN ('ABERTO','EM_ANALISE','GEROU_SMV','IMPROCEDENTE','CANCELADO')),
    fiscal_id        bigint REFERENCES usuarios(id),        -- definido pelo centro de custo do veiculo
    analisado_por    bigint REFERENCES usuarios(id),
    analisado_em     timestamptz,
    motivo_decisao   text,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    atualizado_em    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, numero)
);

CREATE TABLE smv (                                  -- Solicitacao de Manutencao Veicular
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id        bigint NOT NULL REFERENCES municipios(id),
    numero              varchar(20) NOT NULL,
    chamado_id          bigint REFERENCES chamados(id),
    veiculo_id          bigint NOT NULL REFERENCES veiculos(id),
    fornecedor_id       bigint REFERENCES fornecedores(id),    -- oficina/locadora
    contrato_id         bigint REFERENCES contratos(id),
    centro_custo_id     bigint REFERENCES centros_custo(id),
    tipo                varchar(10) NOT NULL CHECK (tipo IN ('PREVENTIVA','CORRETIVA','SINISTRO')),
    etapa               varchar(12) NOT NULL DEFAULT 'ENTRADA'
                        CHECK (etapa IN ('ENTRADA','DIAGNOSTICO','ORCAMENTO','EXECUCAO','ENTREGA','NOTA_FISCAL','CONCLUIDA','CANCELADA')),
    entrada_em          timestamptz,
    entrada_km          integer,
    entrada_tanque      varchar(4),
    defeito_relatado    text,
    veiculo_substituto_id bigint REFERENCES veiculos(id),
    substituto_inicio   timestamptz,
    substituto_fim      timestamptz,
    diagnostico         text,
    saida_em            timestamptz,
    saida_km            integer,
    saida_tanque        varchar(4),
    observacao_entrega  text,
    concluida_em        timestamptz,
    concluida_por       bigint REFERENCES usuarios(id),
    criado_por          bigint REFERENCES usuarios(id),
    criado_em           timestamptz NOT NULL DEFAULT now(),
    atualizado_em       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, numero)
);
CREATE INDEX ON smv (municipio_id, veiculo_id);
CREATE INDEX ON smv (municipio_id, etapa);

ALTER TABLE checklist_execucoes ADD CONSTRAINT fk_checklist_smv FOREIGN KEY (smv_id) REFERENCES smv(id);

CREATE TABLE smv_etapas_hist (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    smv_id        bigint NOT NULL REFERENCES smv(id) ON DELETE CASCADE,
    etapa         varchar(12) NOT NULL,
    usuario_id    bigint REFERENCES usuarios(id),
    observacao    text,
    em            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE smv_mensagens (                        -- chat prefeitura x oficina, preso a SMV (anexos: foto, audio, video, PDF)
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    smv_id        bigint NOT NULL REFERENCES smv(id) ON DELETE CASCADE,
    autor_id      bigint NOT NULL REFERENCES usuarios(id),
    texto         text,
    criado_em     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orcamentos (                           -- a oficina pode enviar revisoes do mesmo orcamento
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id      bigint NOT NULL REFERENCES municipios(id),
    smv_id            bigint NOT NULL REFERENCES smv(id),
    empenho_id        bigint REFERENCES empenhos(id),
    numero            varchar(30) NOT NULL,
    revisao           smallint NOT NULL DEFAULT 1,
    ano               smallint NOT NULL,
    mes               smallint NOT NULL CHECK (mes BETWEEN 1 AND 12),
    status            varchar(12) NOT NULL DEFAULT 'RECEBIDO'
                      CHECK (status IN ('RECEBIDO','EM_ANALISE','REVISAO','APROVADO','REPROVADO')),
    valor_inicial     numeric(14,2) NOT NULL DEFAULT 0,     -- valor enviado pela oficina na 1a revisao
    valor_pecas       numeric(14,2) NOT NULL DEFAULT 0,
    valor_servicos    numeric(14,2) NOT NULL DEFAULT 0,
    valor_total       numeric(14,2) GENERATED ALWAYS AS (valor_pecas + valor_servicos) STORED,
    valor_economizado numeric(14,2) GENERATED ALWAYS AS (valor_inicial - (valor_pecas + valor_servicos)) STORED,
    nf_pecas_numero   varchar(30),
    nf_servicos_numero varchar(30),
    nf_emissao        date,
    enviado_em        timestamptz,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    atualizado_em     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, numero, revisao)
);

ALTER TABLE empenho_lancamentos ADD CONSTRAINT fk_lancamento_orcamento FOREIGN KEY (orcamento_id) REFERENCES orcamentos(id);

CREATE TABLE orcamento_itens (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id     bigint NOT NULL REFERENCES municipios(id),
    orcamento_id     bigint NOT NULL REFERENCES orcamentos(id) ON DELETE CASCADE,
    categoria_id     bigint REFERENCES categorias_servico(id),
    tipo             varchar(7) NOT NULL CHECK (tipo IN ('PECA','SERVICO')),
    codigo           varchar(40),
    descricao        text NOT NULL,
    quantidade       numeric(10,3) NOT NULL DEFAULT 1,
    valor_unitario   numeric(12,2) NOT NULL,
    valor_referencia numeric(12,2),                         -- preco pesquisado/contratado, para comparar
    valor_total      numeric(14,2) GENERATED ALWAYS AS (quantidade * valor_unitario) STORED
);

CREATE TABLE orcamento_aprovacoes (                 -- as 3 assinaturas exigidas
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    orcamento_id  bigint NOT NULL REFERENCES orcamentos(id) ON DELETE CASCADE,
    sequencia     smallint NOT NULL,
    usuario_id    bigint NOT NULL REFERENCES usuarios(id),
    decisao       varchar(10) NOT NULL DEFAULT 'PENDENTE' CHECK (decisao IN ('PENDENTE','APROVADO','REPROVADO')),
    decidido_em   timestamptz,
    observacao    text,
    UNIQUE (orcamento_id, sequencia)
);

CREATE TABLE planos_preventivos (                   -- revisoes por km, horas ou dias
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id   bigint NOT NULL REFERENCES municipios(id),
    nome           varchar(80) NOT NULL,                -- ex: troca de oleo, revisao 10.000 km
    veiculo_id     bigint REFERENCES veiculos(id),
    modelo_id      bigint REFERENCES modelos(id),
    categoria_id   bigint REFERENCES categorias_veiculo(id),
    intervalo_km   integer,
    intervalo_horas integer,
    intervalo_dias integer,
    ativo          boolean NOT NULL DEFAULT true,
    CHECK (veiculo_id IS NOT NULL OR modelo_id IS NOT NULL OR categoria_id IS NOT NULL),
    CHECK (intervalo_km IS NOT NULL OR intervalo_horas IS NOT NULL OR intervalo_dias IS NOT NULL)
);

CREATE TABLE preventivas_realizadas (               -- ultima execucao de cada plano por veiculo (base do alerta)
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    plano_id      bigint NOT NULL REFERENCES planos_preventivos(id),
    veiculo_id    bigint NOT NULL REFERENCES veiculos(id),
    smv_id        bigint REFERENCES smv(id),
    realizada_em  date NOT NULL,
    odometro      integer,
    horimetro     numeric(10,1)
);

-- =====================================================================
-- 10. ABASTECIMENTO (importado da Prime Beneficios) E DESPESAS
-- =====================================================================
CREATE TABLE cartoes (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    fornecedor_id bigint REFERENCES fornecedores(id),   -- operadora (Prime)
    numero_final  varchar(8) NOT NULL,                  -- so os ultimos digitos; nunca o numero completo
    veiculo_id    bigint REFERENCES veiculos(id),
    motorista_id  bigint REFERENCES motoristas(id),
    situacao      varchar(10) NOT NULL DEFAULT 'ATIVO' CHECK (situacao IN ('ATIVO','BLOQUEADO','CANCELADO')),
    criado_em     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE postos (                               -- postos da rede credenciada (vem da Prime)
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id     bigint NOT NULL REFERENCES municipios(id),
    cnpj             varchar(14) NOT NULL,
    nome             text NOT NULL,                     -- nome fantasia
    razao_social     text,
    endereco         text,
    cidade           varchar(80),
    uf               varchar(2),
    latitude         numeric(9,6),
    longitude        numeric(9,6),
    interno          boolean NOT NULL DEFAULT false,    -- posto interno da prefeitura
    codigo_terminal  varchar(30),
    UNIQUE (municipio_id, cnpj)
);

CREATE TABLE abastecimentos (                       -- importado da Prime; pode ser alterado/inativado depois pela Prime
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id     bigint NOT NULL REFERENCES municipios(id),
    id_externo       varchar(60),                       -- codAbastecimento da Prime (chave do upsert)
    veiculo_id       bigint REFERENCES veiculos(id),    -- nulo ate a placa ser vinculada a um veiculo cadastrado
    placa_externa    varchar(8),
    motorista_id     bigint REFERENCES motoristas(id),  -- achado por CPF/registro na importacao
    condutor_nome    text,
    condutor_registro varchar(30),
    cartao_id        bigint REFERENCES cartoes(id),
    posto_id         bigint REFERENCES postos(id),
    contrato_id      bigint REFERENCES contratos(id),
    combustivel_id   smallint REFERENCES combustiveis(id),
    combustivel_externo varchar(40),
    data_hora        timestamptz NOT NULL,
    odometro         integer,                           -- kmAtual
    km_anterior      integer,                           -- kmAnterior
    km_atualizado_em timestamptz,                       -- data_atualizacao_km (muda quando a Prime corrige o km)
    litros           numeric(8,3) CHECK (litros IS NULL OR litros >= 0),
    valor_litro      numeric(8,4),
    valor_total      numeric(12,2) NOT NULL,
    tanque_cheio     boolean,                           -- a Prime nao informa; so no lancamento manual
    tipo_servico     varchar(30),                       -- abastecimento, lavagem etc.
    nome_servico     varchar(80),
    status           varchar(10) NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO','INATIVO')),
    fora_da_rede     boolean NOT NULL DEFAULT false,
    origem           varchar(10) NOT NULL DEFAULT 'API' CHECK (origem IN ('API','MANUAL','IMPORTACAO')),
    observacao       text,
    alerta           varchar(30),                       -- preenchido pelas regras de anomalia
    payload          jsonb,                             -- registro original SEM CPF/CNH do condutor
    criado_em        timestamptz NOT NULL DEFAULT now(),
    atualizado_em    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (municipio_id, id_externo)
);
CREATE INDEX ON abastecimentos (municipio_id, veiculo_id, data_hora);
CREATE INDEX ON abastecimentos (municipio_id, placa_externa) WHERE veiculo_id IS NULL;

CREATE TABLE integracao_logs (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id     bigint NOT NULL REFERENCES municipios(id),
    fonte            varchar(20) NOT NULL,              -- PRIME
    janela_inicio    date,
    janela_fim       date,
    iniciado_em      timestamptz NOT NULL DEFAULT now(),
    finalizado_em    timestamptz,
    paginas          integer NOT NULL DEFAULT 0,
    registros_lidos  integer NOT NULL DEFAULT 0,
    registros_novos  integer NOT NULL DEFAULT 0,
    registros_alterados integer NOT NULL DEFAULT 0,
    status           varchar(10) NOT NULL DEFAULT 'EXECUTANDO' CHECK (status IN ('EXECUTANDO','OK','ERRO')),
    mensagem         text
);

CREATE TABLE despesas (                             -- pedagio, zona azul, estacionamento, refeicao...
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    veiculo_id    bigint REFERENCES veiculos(id),
    motorista_id  bigint REFERENCES motoristas(id),
    ficha_id      bigint REFERENCES fichas_trafego(id),
    tipo          varchar(20) NOT NULL,
    data_despesa  date NOT NULL,
    valor         numeric(12,2) NOT NULL,
    descricao     text,
    criado_em     timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 11. DOCUMENTOS, MULTAS E SINISTROS
-- =====================================================================
CREATE TABLE documentos_veiculo (                   -- CRLV, IPVA, licenciamento, seguro, vistoria
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    veiculo_id    bigint NOT NULL REFERENCES veiculos(id),
    tipo          varchar(20) NOT NULL,
    exercicio     smallint,
    vencimento    date,
    valor         numeric(12,2),
    pago_em       date,
    observacao    text
);
CREATE INDEX ON documentos_veiculo (municipio_id, vencimento);

CREATE TABLE multas (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id    bigint NOT NULL REFERENCES municipios(id),
    veiculo_id      bigint NOT NULL REFERENCES veiculos(id),
    motorista_id    bigint REFERENCES motoristas(id),
    ficha_id        bigint REFERENCES fichas_trafego(id),   -- ajuda a identificar o condutor
    auto_infracao   varchar(30) NOT NULL,
    codigo_infracao varchar(10),
    descricao       text,
    data_hora       timestamptz NOT NULL,
    local_infracao  text,
    pontos          smallint,
    valor           numeric(12,2),
    vencimento      date,
    status          varchar(20) NOT NULL DEFAULT 'ABERTA'
                    CHECK (status IN ('ABERTA','INDICADO_CONDUTOR','RECURSO','PAGA','CANCELADA')),
    UNIQUE (municipio_id, auto_infracao)
);

CREATE TABLE sinistros (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id    bigint NOT NULL REFERENCES municipios(id),
    veiculo_id      bigint NOT NULL REFERENCES veiculos(id),
    motorista_id    bigint REFERENCES motoristas(id),
    ficha_id        bigint REFERENCES fichas_trafego(id),
    smv_id          bigint REFERENCES smv(id),
    data_hora       timestamptz NOT NULL,
    local_sinistro  text,
    descricao       text,
    boletim_ocorrencia varchar(30),
    numero_processo varchar(30),
    houve_vitima    boolean NOT NULL DEFAULT false,
    valor_estimado  numeric(12,2),
    status          varchar(15) NOT NULL DEFAULT 'ABERTO'
);

-- =====================================================================
-- 12. TRANSVERSAIS: NOTIFICACOES, ANEXOS, AUDITORIA
-- =====================================================================
CREATE TABLE notificacoes (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    usuario_id    bigint REFERENCES usuarios(id),
    email_destino citext,
    canal         varchar(6) NOT NULL DEFAULT 'EMAIL' CHECK (canal IN ('EMAIL','APP')),
    assunto       text NOT NULL,
    corpo         text,
    entidade      varchar(40),                          -- ex: smv, solicitacoes_veiculo, motoristas
    entidade_id   bigint,
    status        varchar(10) NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE','ENVIADA','ERRO','LIDA')),
    criado_em     timestamptz NOT NULL DEFAULT now(),
    enviada_em    timestamptz
);
CREATE INDEX ON notificacoes (municipio_id, status);

CREATE TABLE anexos (                               -- fotos, audios, videos, PDFs (referencia ao armazenamento)
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL REFERENCES municipios(id),
    entidade      varchar(40) NOT NULL,                 -- 'veiculos', 'motoristas', 'orcamentos', 'smv_mensagens', 'sinistros'...
    entidade_id   bigint NOT NULL,
    categoria     varchar(20),                          -- CRLV, CNH, FOTO_FRENTE, NOTA_FISCAL, ORCAMENTO, BO...
    nome_arquivo  text NOT NULL,
    mime_type     varchar(100),
    tamanho_bytes bigint,
    storage_path  text NOT NULL,
    hash_sha256   varchar(64),
    enviado_por   bigint REFERENCES usuarios(id),
    criado_em     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON anexos (municipio_id, entidade, entidade_id);

CREATE TABLE auditoria (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_id  bigint NOT NULL,
    usuario_id    bigint,
    tabela        text NOT NULL,
    registro_id   bigint,
    acao          varchar(1) NOT NULL CHECK (acao IN ('I','U','D')),
    dados_antes   jsonb,
    dados_depois  jsonb,
    em            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON auditoria (municipio_id, tabela, registro_id);

-- =====================================================================
-- 13. VIEWS DE INDICADORES (todas respeitam RLS)
-- =====================================================================
CREATE VIEW vw_saldo_empenho WITH (security_invoker = true) AS
SELECT e.id AS empenho_id, e.municipio_id, e.centro_custo_id, e.contrato_id, e.numero, e.exercicio,
       e.valor_empenhado,
       COALESCE(SUM(l.valor) FILTER (WHERE l.tipo = 'RESERVA'), 0) AS reservado,
       COALESCE(SUM(l.valor) FILTER (WHERE l.tipo = 'CONSUMO'), 0) AS consumido,
       COALESCE(SUM(l.valor) FILTER (WHERE l.tipo = 'ESTORNO'), 0) AS estornado,
       e.valor_empenhado
         - COALESCE(SUM(l.valor) FILTER (WHERE l.tipo IN ('RESERVA','CONSUMO')), 0)
         + COALESCE(SUM(l.valor) FILTER (WHERE l.tipo = 'ESTORNO'), 0) AS saldo
FROM empenhos e
LEFT JOIN empenho_lancamentos l ON l.empenho_id = e.id
GROUP BY e.id;

CREATE VIEW vw_consumo_veiculo WITH (security_invoker = true) AS
SELECT a.municipio_id, a.veiculo_id, a.id AS abastecimento_id, a.data_hora, a.litros,
       COALESCE(a.odometro - a.km_anterior, a.odometro - LAG(a.odometro) OVER w) AS km_rodados,
       ROUND(COALESCE(a.odometro - a.km_anterior, a.odometro - LAG(a.odometro) OVER w)::numeric
             / NULLIF(a.litros, 0), 2) AS km_por_litro      -- aproximacao: assume tanque cheio
FROM abastecimentos a
WHERE a.status = 'ATIVO' AND a.litros > 0 AND a.odometro IS NOT NULL AND a.veiculo_id IS NOT NULL
WINDOW w AS (PARTITION BY a.municipio_id, a.veiculo_id ORDER BY a.data_hora);

CREATE VIEW vw_dias_em_manutencao WITH (security_invoker = true) AS
SELECT s.id AS smv_id, s.municipio_id, s.veiculo_id, s.numero, s.etapa,
       GREATEST(0, (COALESCE(s.saida_em, now())::date - s.entrada_em::date)) AS dias_em_manutencao
FROM smv s
WHERE s.entrada_em IS NOT NULL;

-- =====================================================================
-- 14. TRIGGERS updated_at E ROW LEVEL SECURITY (automaticos)
-- =====================================================================
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT table_name FROM information_schema.columns
           WHERE table_schema = 'frota' AND column_name = 'atualizado_em'
  LOOP
    EXECUTE format('CREATE TRIGGER trg_%I_upd BEFORE UPDATE ON frota.%I
                    FOR EACH ROW EXECUTE FUNCTION frota.set_updated_at()', t, t);
  END LOOP;

  FOR t IN SELECT c.table_name FROM information_schema.columns c
           JOIN information_schema.tables tb USING (table_schema, table_name)
           WHERE c.table_schema = 'frota' AND c.column_name = 'municipio_id'
             AND tb.table_type = 'BASE TABLE'
  LOOP
    EXECUTE format('ALTER TABLE frota.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON frota.%I
                    USING (municipio_id = frota.municipio_atual())
                    WITH CHECK (municipio_id = frota.municipio_atual())', t);
  END LOOP;
END $$;

-- Observacoes:
-- * Role da aplicacao: sem BYPASSRLS e que nao seja dona das tabelas. 'municipios' fica fora da RLS.
-- * FKs nao garantem sozinhas que dois registros sao da mesma prefeitura: validar nos servicos e nos testes.
-- * Volume alto: ficha_pontos_gps, auditoria e notificacoes -> particionar por data quando crescer.
