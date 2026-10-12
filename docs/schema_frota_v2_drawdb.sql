CREATE TABLE municipios (
  id bigserial PRIMARY KEY,
  nome text NOT NULL,
  uf varchar(2) NOT NULL,
  cnpj varchar(14) NOT NULL UNIQUE,
  codigo_ibge varchar(7),
  config jsonb NOT NULL DEFAULT '{}',
  ativo boolean NOT NULL DEFAULT true,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE secretarias (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  sigla varchar(20) NOT NULL,
  nome text NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, sigla)
);

CREATE TABLE unidades (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  secretaria_id bigint NOT NULL REFERENCES secretarias(id),
  nome text NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (secretaria_id, nome)
);

CREATE TABLE centros_custo (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  secretaria_id bigint REFERENCES secretarias(id),
  codigo varchar(30) NOT NULL,
  nome text NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  UNIQUE (municipio_id, codigo)
);

CREATE TABLE perfis (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  codigo varchar(30) NOT NULL,
  nome varchar(60) NOT NULL,
  permissoes jsonb NOT NULL DEFAULT '[]',
  UNIQUE (municipio_id, codigo)
);

CREATE TABLE usuarios (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  perfil_id bigint NOT NULL REFERENCES perfis(id),
  secretaria_id bigint REFERENCES secretarias(id),
  unidade_id bigint REFERENCES unidades(id),
  fornecedor_id bigint,
  nome text NOT NULL,
  email varchar(255) NOT NULL,
  cpf varchar(11),
  matricula varchar(20),
  senha_hash text NOT NULL,
  ativo boolean NOT NULL DEFAULT true,
  ultimo_login timestamp,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, email)
);

CREATE TABLE marcas (
  id bigserial PRIMARY KEY,
  nome text NOT NULL UNIQUE
);

CREATE TABLE modelos (
  id bigserial PRIMARY KEY,
  marca_id bigint NOT NULL REFERENCES marcas(id),
  nome text NOT NULL,
  UNIQUE (marca_id, nome)
);

CREATE TABLE combustiveis (
  id smallserial PRIMARY KEY,
  nome varchar(30) NOT NULL UNIQUE
);

CREATE TABLE categorias_veiculo (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  nome varchar(60) NOT NULL,
  cnh_minima varchar(5),
  usa_horimetro boolean NOT NULL DEFAULT false,
  UNIQUE (municipio_id, nome)
);

CREATE TABLE categorias_servico (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  nome varchar(60) NOT NULL,
  UNIQUE (municipio_id, nome)
);

CREATE TABLE fornecedores (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  cnpj_cpf varchar(14) NOT NULL,
  razao_social text NOT NULL,
  tipo varchar(20) NOT NULL,
  telefone varchar(20),
  email varchar(255),
  ativo boolean NOT NULL DEFAULT true,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, cnpj_cpf)
);

CREATE TABLE contratos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  fornecedor_id bigint NOT NULL REFERENCES fornecedores(id),
  tipo varchar(20) NOT NULL,
  numero varchar(40) NOT NULL,
  processo varchar(40),
  objeto text NOT NULL,
  vigencia_ini date NOT NULL,
  vigencia_fim date NOT NULL,
  valor_total numeric(14,2),
  ativo boolean NOT NULL DEFAULT true,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, numero)
);

CREATE TABLE fiscais_contrato (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  contrato_id bigint NOT NULL REFERENCES contratos(id),
  centro_custo_id bigint REFERENCES centros_custo(id),
  usuario_id bigint NOT NULL REFERENCES usuarios(id),
  suplente boolean NOT NULL DEFAULT false,
  vigencia_ini date NOT NULL DEFAULT current_date,
  vigencia_fim date
);

CREATE TABLE empenhos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  contrato_id bigint NOT NULL REFERENCES contratos(id),
  centro_custo_id bigint NOT NULL REFERENCES centros_custo(id),
  numero varchar(30) NOT NULL,
  exercicio smallint NOT NULL,
  valor_empenhado numeric(14,2) NOT NULL,
  data_empenho date,
  ativo boolean NOT NULL DEFAULT true,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, exercicio, numero)
);

CREATE TABLE empenho_lancamentos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  empenho_id bigint NOT NULL REFERENCES empenhos(id),
  tipo varchar(10) NOT NULL,
  valor numeric(14,2) NOT NULL,
  orcamento_id bigint,
  observacao text,
  criado_por bigint REFERENCES usuarios(id),
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE veiculos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  secretaria_id bigint REFERENCES secretarias(id),
  unidade_id bigint REFERENCES unidades(id),
  centro_custo_id bigint REFERENCES centros_custo(id),
  categoria_id bigint REFERENCES categorias_veiculo(id),
  modelo_id bigint REFERENCES modelos(id),
  combustivel_id smallint REFERENCES combustiveis(id),
  placa varchar(8) NOT NULL,
  prefixo varchar(20),
  patrimonio varchar(30),
  renavam varchar(11),
  chassi varchar(17),
  ano_fabricacao smallint,
  ano_modelo smallint,
  cor varchar(30),
  motor varchar(60),
  transmissao varchar(20),
  capacidade_tanque numeric(6,2),
  consumo_referencia numeric(5,2),
  capacidade_passageiros smallint,
  odometro_atual integer NOT NULL DEFAULT 0,
  horimetro_atual numeric(10,1),
  km_entrada integer,
  estado_conservacao varchar(10),
  situacao varchar(15) NOT NULL DEFAULT 'DISPONIVEL',
  tipo_frota varchar(10) NOT NULL DEFAULT 'PROPRIO',
  proprietario text,
  contrato_locacao_id bigint REFERENCES contratos(id),
  valor_fipe numeric(14,2),
  valor_aquisicao numeric(14,2),
  valor_aluguel_mensal numeric(14,2),
  data_aquisicao date,
  data_baixa date,
  motivo_baixa text,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, placa)
);

CREATE TABLE veiculo_equipamentos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id) ON DELETE CASCADE,
  descricao varchar(100) NOT NULL,
  observacao text
);

CREATE TABLE veiculo_lotacoes (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  secretaria_id bigint REFERENCES secretarias(id),
  unidade_id bigint REFERENCES unidades(id),
  centro_custo_id bigint REFERENCES centros_custo(id),
  inicio date NOT NULL,
  fim date
);

CREATE TABLE leituras_veiculo (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  odometro integer,
  horimetro numeric(10,1),
  lido_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  origem varchar(20) NOT NULL,
  origem_id bigint
);

CREATE TABLE motoristas (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  usuario_id bigint REFERENCES usuarios(id),
  secretaria_id bigint REFERENCES secretarias(id),
  unidade_id bigint REFERENCES unidades(id),
  prontuario varchar(20) NOT NULL,
  nome text NOT NULL,
  cpf varchar(11) NOT NULL,
  rg varchar(20),
  rg_emissor varchar(20),
  data_nascimento date,
  cargo varchar(80),
  telefone varchar(20),
  email varchar(255),
  endereco text,
  cep varchar(8),
  cnh_numero varchar(11),
  cnh_categoria varchar(5),
  cnh_emissao date,
  cnh_validade date,
  cnh_orgao varchar(20),
  situacao varchar(10) NOT NULL DEFAULT 'ATIVO',
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, prontuario),
  UNIQUE (municipio_id, cpf)
);

CREATE TABLE motorista_certificados (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  motorista_id bigint NOT NULL REFERENCES motoristas(id),
  curso text NOT NULL,
  instituicao text,
  realizado_em date,
  validade date
);

CREATE TABLE motorista_penalidades (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  motorista_id bigint NOT NULL REFERENCES motoristas(id),
  descricao text NOT NULL,
  penalidade text,
  aplicada_em date
);

CREATE TABLE motorista_afastamentos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  motorista_id bigint NOT NULL REFERENCES motoristas(id),
  tipo varchar(10) NOT NULL,
  inicio date NOT NULL,
  fim date NOT NULL
);

CREATE TABLE solicitacoes_veiculo (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  numero varchar(20) NOT NULL,
  solicitante_id bigint NOT NULL REFERENCES usuarios(id),
  secretaria_id bigint NOT NULL REFERENCES secretarias(id),
  unidade_id bigint REFERENCES unidades(id),
  categoria_id bigint REFERENCES categorias_veiculo(id),
  saida_prevista timestamp NOT NULL,
  retorno_previsto timestamp NOT NULL,
  origem text,
  destino text NOT NULL,
  passageiros smallint,
  finalidade text NOT NULL,
  prioridade varchar(10) NOT NULL DEFAULT 'NORMAL',
  status_aprovacao varchar(10) NOT NULL DEFAULT 'PENDENTE',
  status_andamento varchar(12) NOT NULL DEFAULT 'PENDENTE',
  veiculo_id bigint REFERENCES veiculos(id),
  motorista_id bigint REFERENCES motoristas(id),
  analisado_por bigint REFERENCES usuarios(id),
  analisado_em timestamp,
  motivo_decisao text,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, numero)
);

CREATE TABLE fichas_trafego (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  client_uuid uuid NOT NULL,
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  motorista_id bigint NOT NULL REFERENCES motoristas(id),
  solicitacao_id bigint REFERENCES solicitacoes_veiculo(id),
  secretaria_id bigint REFERENCES secretarias(id),
  unidade_id bigint REFERENCES unidades(id),
  data_ficha date NOT NULL,
  departamento_requisitante text,
  plantao_inicio time,
  plantao_fim time,
  km_inicial integer,
  km_final integer,
  horimetro_inicial numeric(10,1),
  horimetro_final numeric(10,1),
  status varchar(15) NOT NULL DEFAULT 'RASCUNHO',
  origem_registro varchar(10) NOT NULL DEFAULT 'APP',
  assinada_em timestamp,
  enviada_em timestamp,
  sincronizada_em timestamp,
  validada_por bigint REFERENCES usuarios(id),
  validada_em timestamp,
  conferida_por bigint REFERENCES usuarios(id),
  conferida_em timestamp,
  motivo_devolucao text,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, client_uuid)
);

CREATE TABLE ficha_trechos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  ficha_id bigint NOT NULL REFERENCES fichas_trafego(id) ON DELETE CASCADE,
  sequencia smallint NOT NULL,
  partida_em timestamp,
  km_partida integer,
  itinerario text,
  chegada_em timestamp,
  km_chegada integer,
  usuario_nome text,
  UNIQUE (ficha_id, sequencia)
);

CREATE TABLE ficha_pontos_gps (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  ficha_id bigint NOT NULL REFERENCES fichas_trafego(id) ON DELETE CASCADE,
  trecho_id bigint REFERENCES ficha_trechos(id) ON DELETE CASCADE,
  capturado_em timestamp NOT NULL,
  latitude numeric(9,6) NOT NULL,
  longitude numeric(9,6) NOT NULL,
  precisao_m numeric(7,1)
);

CREATE TABLE ficha_historico (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  ficha_id bigint NOT NULL REFERENCES fichas_trafego(id) ON DELETE CASCADE,
  acao varchar(20) NOT NULL,
  usuario_id bigint REFERENCES usuarios(id),
  observacao text,
  em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE checklist_modelos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  nome varchar(80) NOT NULL,
  finalidade varchar(15) NOT NULL,
  categoria_id bigint REFERENCES categorias_veiculo(id),
  ativo boolean NOT NULL DEFAULT true
);

CREATE TABLE checklist_itens (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  modelo_id bigint NOT NULL REFERENCES checklist_modelos(id) ON DELETE CASCADE,
  grupo varchar(40) NOT NULL,
  descricao varchar(120) NOT NULL,
  sequencia smallint NOT NULL DEFAULT 0,
  critico boolean NOT NULL DEFAULT false
);

CREATE TABLE checklist_execucoes (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  modelo_id bigint NOT NULL REFERENCES checklist_modelos(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  motorista_id bigint REFERENCES motoristas(id),
  ficha_id bigint REFERENCES fichas_trafego(id),
  smv_id bigint,
  momento varchar(15) NOT NULL,
  executado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  odometro integer,
  nivel_combustivel varchar(4),
  tem_irregularidade boolean NOT NULL DEFAULT false
);

CREATE TABLE checklist_respostas (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  execucao_id bigint NOT NULL REFERENCES checklist_execucoes(id) ON DELETE CASCADE,
  item_id bigint NOT NULL REFERENCES checklist_itens(id),
  conforme boolean NOT NULL,
  observacao text
);

CREATE TABLE chamados (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  numero varchar(20) NOT NULL,
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  aberto_por bigint NOT NULL REFERENCES usuarios(id),
  origem varchar(12) NOT NULL DEFAULT 'MANUAL',
  checklist_execucao_id bigint REFERENCES checklist_execucoes(id),
  descricao text NOT NULL,
  prioridade varchar(10) NOT NULL DEFAULT 'NORMAL',
  status varchar(15) NOT NULL DEFAULT 'ABERTO',
  fiscal_id bigint REFERENCES usuarios(id),
  analisado_por bigint REFERENCES usuarios(id),
  analisado_em timestamp,
  motivo_decisao text,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, numero)
);

CREATE TABLE smv (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  numero varchar(20) NOT NULL,
  chamado_id bigint REFERENCES chamados(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  fornecedor_id bigint REFERENCES fornecedores(id),
  contrato_id bigint REFERENCES contratos(id),
  centro_custo_id bigint REFERENCES centros_custo(id),
  tipo varchar(10) NOT NULL,
  etapa varchar(12) NOT NULL DEFAULT 'ENTRADA',
  entrada_em timestamp,
  entrada_km integer,
  entrada_tanque varchar(4),
  defeito_relatado text,
  veiculo_substituto_id bigint REFERENCES veiculos(id),
  substituto_inicio timestamp,
  substituto_fim timestamp,
  diagnostico text,
  saida_em timestamp,
  saida_km integer,
  saida_tanque varchar(4),
  observacao_entrega text,
  concluida_em timestamp,
  concluida_por bigint REFERENCES usuarios(id),
  criado_por bigint REFERENCES usuarios(id),
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, numero)
);

CREATE TABLE smv_etapas_hist (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  smv_id bigint NOT NULL REFERENCES smv(id) ON DELETE CASCADE,
  etapa varchar(12) NOT NULL,
  usuario_id bigint REFERENCES usuarios(id),
  observacao text,
  em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE smv_mensagens (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  smv_id bigint NOT NULL REFERENCES smv(id) ON DELETE CASCADE,
  autor_id bigint NOT NULL REFERENCES usuarios(id),
  texto text,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orcamentos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  smv_id bigint NOT NULL REFERENCES smv(id),
  empenho_id bigint REFERENCES empenhos(id),
  numero varchar(30) NOT NULL,
  revisao smallint NOT NULL DEFAULT 1,
  ano smallint NOT NULL,
  mes smallint NOT NULL,
  status varchar(12) NOT NULL DEFAULT 'RECEBIDO',
  valor_inicial numeric(14,2) NOT NULL DEFAULT 0,
  valor_pecas numeric(14,2) NOT NULL DEFAULT 0,
  valor_servicos numeric(14,2) NOT NULL DEFAULT 0,
  valor_total numeric(14,2),
  valor_economizado numeric(14,2),
  nf_pecas_numero varchar(30),
  nf_servicos_numero varchar(30),
  nf_emissao date,
  enviado_em timestamp,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, numero, revisao)
);

CREATE TABLE orcamento_itens (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  orcamento_id bigint NOT NULL REFERENCES orcamentos(id) ON DELETE CASCADE,
  categoria_id bigint REFERENCES categorias_servico(id),
  tipo varchar(7) NOT NULL,
  codigo varchar(40),
  descricao text NOT NULL,
  quantidade numeric(10,3) NOT NULL DEFAULT 1,
  valor_unitario numeric(12,2) NOT NULL,
  valor_referencia numeric(12,2),
  valor_total numeric(14,2)
);

CREATE TABLE orcamento_aprovacoes (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  orcamento_id bigint NOT NULL REFERENCES orcamentos(id) ON DELETE CASCADE,
  sequencia smallint NOT NULL,
  usuario_id bigint NOT NULL REFERENCES usuarios(id),
  decisao varchar(10) NOT NULL DEFAULT 'PENDENTE',
  decidido_em timestamp,
  observacao text,
  UNIQUE (orcamento_id, sequencia)
);

CREATE TABLE planos_preventivos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  nome varchar(80) NOT NULL,
  veiculo_id bigint REFERENCES veiculos(id),
  modelo_id bigint REFERENCES modelos(id),
  categoria_id bigint REFERENCES categorias_veiculo(id),
  intervalo_km integer,
  intervalo_horas integer,
  intervalo_dias integer,
  ativo boolean NOT NULL DEFAULT true
);

CREATE TABLE preventivas_realizadas (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  plano_id bigint NOT NULL REFERENCES planos_preventivos(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  smv_id bigint REFERENCES smv(id),
  realizada_em date NOT NULL,
  odometro integer,
  horimetro numeric(10,1)
);

CREATE TABLE cartoes (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  fornecedor_id bigint REFERENCES fornecedores(id),
  numero_final varchar(8) NOT NULL,
  veiculo_id bigint REFERENCES veiculos(id),
  motorista_id bigint REFERENCES motoristas(id),
  situacao varchar(10) NOT NULL DEFAULT 'ATIVO',
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE postos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  cnpj varchar(14) NOT NULL,
  nome text NOT NULL,
  razao_social text,
  endereco text,
  cidade varchar(80),
  uf varchar(2),
  latitude numeric(9,6),
  longitude numeric(9,6),
  interno boolean NOT NULL DEFAULT false,
  codigo_terminal varchar(30),
  UNIQUE (municipio_id, cnpj)
);

CREATE TABLE abastecimentos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  id_externo varchar(60),
  veiculo_id bigint REFERENCES veiculos(id),
  placa_externa varchar(8),
  motorista_id bigint REFERENCES motoristas(id),
  condutor_nome text,
  condutor_registro varchar(30),
  cartao_id bigint REFERENCES cartoes(id),
  posto_id bigint REFERENCES postos(id),
  contrato_id bigint REFERENCES contratos(id),
  combustivel_id smallint REFERENCES combustiveis(id),
  combustivel_externo varchar(40),
  data_hora timestamp NOT NULL,
  odometro integer,
  km_anterior integer,
  km_atualizado_em timestamp,
  litros numeric(8,3),
  valor_litro numeric(8,4),
  valor_total numeric(12,2) NOT NULL,
  tanque_cheio boolean,
  tipo_servico varchar(30),
  nome_servico varchar(80),
  status varchar(10) NOT NULL DEFAULT 'ATIVO',
  fora_da_rede boolean NOT NULL DEFAULT false,
  origem varchar(10) NOT NULL DEFAULT 'API',
  observacao text,
  alerta varchar(30),
  payload jsonb,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (municipio_id, id_externo)
);

CREATE TABLE integracao_logs (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  fonte varchar(20) NOT NULL,
  janela_inicio date,
  janela_fim date,
  iniciado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finalizado_em timestamp,
  paginas integer NOT NULL DEFAULT 0,
  registros_lidos integer NOT NULL DEFAULT 0,
  registros_novos integer NOT NULL DEFAULT 0,
  registros_alterados integer NOT NULL DEFAULT 0,
  status varchar(10) NOT NULL DEFAULT 'EXECUTANDO',
  mensagem text
);

CREATE TABLE despesas (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  veiculo_id bigint REFERENCES veiculos(id),
  motorista_id bigint REFERENCES motoristas(id),
  ficha_id bigint REFERENCES fichas_trafego(id),
  tipo varchar(20) NOT NULL,
  data_despesa date NOT NULL,
  valor numeric(12,2) NOT NULL,
  descricao text,
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE documentos_veiculo (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  tipo varchar(20) NOT NULL,
  exercicio smallint,
  vencimento date,
  valor numeric(12,2),
  pago_em date,
  observacao text
);

CREATE TABLE multas (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  motorista_id bigint REFERENCES motoristas(id),
  ficha_id bigint REFERENCES fichas_trafego(id),
  auto_infracao varchar(30) NOT NULL,
  codigo_infracao varchar(10),
  descricao text,
  data_hora timestamp NOT NULL,
  local_infracao text,
  pontos smallint,
  valor numeric(12,2),
  vencimento date,
  status varchar(20) NOT NULL DEFAULT 'ABERTA',
  UNIQUE (municipio_id, auto_infracao)
);

CREATE TABLE sinistros (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  veiculo_id bigint NOT NULL REFERENCES veiculos(id),
  motorista_id bigint REFERENCES motoristas(id),
  ficha_id bigint REFERENCES fichas_trafego(id),
  smv_id bigint REFERENCES smv(id),
  data_hora timestamp NOT NULL,
  local_sinistro text,
  descricao text,
  boletim_ocorrencia varchar(30),
  numero_processo varchar(30),
  houve_vitima boolean NOT NULL DEFAULT false,
  valor_estimado numeric(12,2),
  status varchar(15) NOT NULL DEFAULT 'ABERTO'
);

CREATE TABLE notificacoes (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  usuario_id bigint REFERENCES usuarios(id),
  email_destino varchar(255),
  canal varchar(6) NOT NULL DEFAULT 'EMAIL',
  assunto text NOT NULL,
  corpo text,
  entidade varchar(40),
  entidade_id bigint,
  status varchar(10) NOT NULL DEFAULT 'PENDENTE',
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  enviada_em timestamp
);

CREATE TABLE anexos (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL REFERENCES municipios(id),
  entidade varchar(40) NOT NULL,
  entidade_id bigint NOT NULL,
  categoria varchar(20),
  nome_arquivo text NOT NULL,
  mime_type varchar(100),
  tamanho_bytes bigint,
  storage_path text NOT NULL,
  hash_sha256 varchar(64),
  enviado_por bigint REFERENCES usuarios(id),
  criado_em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE auditoria (
  id bigserial PRIMARY KEY,
  municipio_id bigint NOT NULL,
  usuario_id bigint,
  tabela text NOT NULL,
  registro_id bigint,
  acao varchar(1) NOT NULL,
  dados_antes jsonb,
  dados_depois jsonb,
  em timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
