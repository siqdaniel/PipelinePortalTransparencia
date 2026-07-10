-- ============================================================================
-- 0_criar_banco.sql
-- ============================================================================

-- 1. CRIAÇÃO DO BANCO DE DADOS
CREATE DATABASE IF NOT EXISTS transparencia;
USE transparencia;

-- O projeto exige que o processo seja idempotente. 
-- Para a criação do banco, garantimos limpando as tabelas anteriores na ordem correta das FKs.
DROP TABLE IF EXISTS silver_trecho;
DROP TABLE IF EXISTS silver_pagamento;
DROP TABLE IF EXISTS silver_passagem;
DROP TABLE IF EXISTS silver_viagem;

DROP TABLE IF EXISTS raw_trecho;
DROP TABLE IF EXISTS raw_pagamento;
DROP TABLE IF EXISTS raw_passagem;
DROP TABLE IF EXISTS raw_viagem;


-- ============================================================================
-- CAMADA RAW (Cópia fiel do CSV, colunas VARCHAR, sem constraints)
-- ============================================================================

CREATE TABLE raw_viagem (
    id_viagem TEXT,
    num_proposta TEXT,
    situacao TEXT,
    viagem_urgente TEXT,
    cod_orgao_superior TEXT,          -- Alterado para TEXT (Corrige o erro atual)
    nome_orgao_superior TEXT,
    cpf_viajante TEXT,       
    nome_viajante TEXT,
    cargo TEXT,
    funcao TEXT,              
    data_inicio TEXT,
    data_fim TEXT,
    destinos TEXT,                    
    motivo TEXT,                      
    valor_diarias TEXT,               
    valor_passagens TEXT,             
    valor_devolucao TEXT,             
    valor_outros_gastos TEXT          
);

CREATE TABLE raw_passagem (
    id_viagem TEXT,
    meio_transporte TEXT,
    pais_origem_ida TEXT,
    uf_origem_ida TEXT,
    cidade_origem_ida TEXT,
    pais_destino_ida TEXT,
    uf_destino_ida TEXT,
    cidade_destino_ida TEXT,
    dados_volta TEXT,                 
    valor_passagem TEXT,              
    taxa_servico TEXT,                
    data_emissao TEXT
);

CREATE TABLE raw_pagamento (
    id_viagem TEXT,
    num_proposta TEXT,
    nome_orgao_pagador TEXT,
    nome_ug_pagadora TEXT,
    tipo_pagamento TEXT,
    valor TEXT
);

CREATE TABLE raw_trecho (
    id_viagem TEXT,
    sequencia_trecho TEXT,
    origem_data TEXT,
    origem_uf TEXT,
    origem_cidade TEXT,
    destino_data TEXT,
    destino_uf TEXT,
    destino_cidade TEXT,
    meio_transporte TEXT,
    numero_diarias TEXT
);

-- ============================================================================
-- CAMADA SILVER (Dados limpos, tipados, com PK, FK e Constraints)
-- ============================================================================

-- TABELA: silver_viagem
CREATE TABLE silver_viagem (
    id_viagem VARCHAR(20) NOT NULL,
    num_proposta VARCHAR(20),
    situacao VARCHAR(50),
    viagem_urgente VARCHAR(5),
    cod_orgao_superior VARCHAR(20),
    nome_orgao_superior VARCHAR(255) NOT NULL, -- Constraint 1 (Exigência do PDF)
    nome_viajante VARCHAR(255),
    cargo VARCHAR(255),
    data_inicio DATE,
    data_fim DATE,
    destinos VARCHAR(4000),
    motivo VARCHAR(4000),
    valor_diarias DECIMAL(10,2),
    valor_passagens DECIMAL(10,2),
    valor_devolucao DECIMAL(10,2),
    valor_outros_gastos DECIMAL(10,2),
    valor_total DECIMAL(12,2),                 -- Calculado na etapa de transformação
    duracao_dias INT,                          -- Calculado na etapa de transformação
    
    PRIMARY KEY (id_viagem),
    CONSTRAINT chk_silver_viagem_valor_diarias CHECK (valor_diarias >= 0) -- Constraint 2 (Exigência do PDF)
);

-- TABELA: silver_passagem
CREATE TABLE silver_passagem (
    id_passagem INT AUTO_INCREMENT,
    id_viagem VARCHAR(20) NOT NULL,
    meio_transporte VARCHAR(50),
    pais_origem_ida VARCHAR(60),
    uf_origem_ida VARCHAR(40),
    cidade_origem_ida VARCHAR(80),
    pais_destino_ida VARCHAR(60),
    uf_destino_ida VARCHAR(40),
    cidade_destino_ida VARCHAR(80),
    valor_passagem DECIMAL(10,2),
    taxa_servico DECIMAL(10,2),
    data_emissao DATE,
    
    PRIMARY KEY (id_passagem),
    FOREIGN KEY (id_viagem) REFERENCES silver_viagem(id_viagem),
    CONSTRAINT chk_silver_passagem_valor CHECK (valor_passagem >= 0),   -- Constraint 1 (Exigência do PDF)
    CONSTRAINT chk_silver_passagem_taxa CHECK (taxa_servico >= 0)       -- Constraint 2 (Exigência do PDF)
);

-- TABELA: silver_pagamento
CREATE TABLE silver_pagamento (
    id_pagamento INT AUTO_INCREMENT,
    id_viagem VARCHAR(20) NOT NULL,
    num_proposta VARCHAR(20),
    nome_orgao_pagador VARCHAR(255),
    nome_ug_pagadora VARCHAR(255),
    tipo_pagamento VARCHAR(50) NOT NULL,                                 -- Constraint 1 (Exigência do PDF)
    valor DECIMAL(10,2),
    
    PRIMARY KEY (id_pagamento),
    FOREIGN KEY (id_viagem) REFERENCES silver_viagem(id_viagem),
    CONSTRAINT chk_silver_pagamento_valor CHECK (valor >= 0)             -- Constraint 2 (Exigência do PDF)
);

-- TABELA: silver_trecho
CREATE TABLE silver_trecho (
    id_trecho INT AUTO_INCREMENT,
    id_viagem VARCHAR(20) NOT NULL,
    sequencia_trecho INT,
    origem_data DATE,
    origem_uf VARCHAR(40),
    origem_cidade VARCHAR(80),
    destino_data DATE,
    destino_uf VARCHAR(40),
    destino_cidade VARCHAR(80),
    meio_transporte VARCHAR(50),
    numero_diarias DECIMAL(10,2),
    
    PRIMARY KEY (id_trecho),
    FOREIGN KEY (id_viagem) REFERENCES silver_viagem(id_viagem),
    CONSTRAINT chk_silver_trecho_diarias CHECK (numero_diarias >= 0),    -- Constraint 1 (Exigência do PDF)
    CONSTRAINT uq_silver_trecho_viagem_seq UNIQUE (id_viagem, sequencia_trecho) -- Constraint 2 (Exigência do PDF)
);