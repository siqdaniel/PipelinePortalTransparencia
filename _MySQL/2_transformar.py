import pandas as pd
import numpy as np
from datetime import datetime
from config import TAMANHO_BLOCO
import banco
import math

def sanitizar_tupla(linha):
    """
    Varre os elementos de uma linha e garante que qualquer tipo de NaN 
    (seja do Pandas ou do NumPy) seja convertido para None puro do Python.
    """
    nova_linha = []
    for x in linha:
        # Verifica se é um float nulo (NaN)
        if isinstance(x, float) and math.isnan(x):
            nova_linha.append(None)
        # Verifica se é o objeto nan do pandas/numpy ou string 'nan'/'None'
        elif pd.isna(x) or x is np.nan or str(x).strip().lower() in ['nan', 'none']:
            nova_linha.append(None)
        else:
            nova_linha.append(x)
    return tuple(nova_linha)


def transformar_viagens(conexao):
    print("Processando e transformando: raw_viagem -> silver_viagem...")
    banco.executar(conexao, "SET FOREIGN_KEY_CHECKS = 0;")
    banco.executar(conexao, "TRUNCATE TABLE silver_viagem;")
    banco.executar(conexao, "SET FOREIGN_KEY_CHECKS = 1;")

    cursor = conexao.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT * FROM raw_viagem")
    
    colunas_silver = [
        'id_viagem', 'num_proposta', 'situacao', 'viagem_urgente', 
        'cod_orgao_superior', 'nome_orgao_superior', 'nome_viajante', 'cargo', 
        'data_inicio', 'data_fim', 'destinos', 'motivo', 
        'valor_diarias', 'valor_passagens', 'valor_devolucao', 'valor_outros_gastos',
        'valor_total', 'duracao_dias'
    ]
    placeholders = ", ".join(["%s"] * len(colunas_silver))
    sql_insert = f"INSERT INTO silver_viagem ({', '.join(colunas_silver)}) VALUES ({placeholders})"

    while True:
        linhas_raw = cursor.fetchmany(TAMANHO_BLOCO)
        if not linhas_raw:
            break
            
        chunk = pd.DataFrame(linhas_raw)
        chunk = chunk.replace(r'^\s*$', np.nan, regex=True).replace('None', np.nan)
        
        chunk['data_inicio'] = pd.to_datetime(chunk['data_inicio'], format='%d/%m/%Y', errors='coerce').dt.date
        chunk['data_fim'] = pd.to_datetime(chunk['data_fim'], format='%d/%m/%Y', errors='coerce').dt.date
        
        colunas_valores = ['valor_diarias', 'valor_passagens', 'valor_devolucao', 'valor_outros_gastos']
        for col in colunas_valores:
            chunk[col] = chunk[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            chunk[col] = pd.to_numeric(chunk[col], errors='coerce').fillna(0.00)
            if col == 'valor_diarias':
                chunk[col] = chunk[col].apply(lambda x: x if x >= 0 else 0.00)

        chunk['valor_total'] = (chunk['valor_diarias'] + chunk['valor_passagens'] + 
                                chunk['valor_outros_gastos'] - chunk['valor_devolucao'])
        
        dt_inicio_serie = pd.to_datetime(chunk['data_inicio'], errors='coerce')
        dt_fim_serie = pd.to_datetime(chunk['data_fim'], errors='coerce')
        chunk['duracao_dias'] = (dt_fim_serie - dt_inicio_serie).dt.days.fillna(0).astype(int)

        chunk['nome_orgao_superior'] = chunk['nome_orgao_superior'].fillna("ÓRGÃO NÃO INFORMADO")
        chunk['id_viagem'] = chunk['id_viagem'].fillna("IGNORADO")
        
        chunk_silver = chunk[colunas_silver].copy()
        
        # BLINDAGEM CRÍTICA: Corta qualquer string que passe do limite do VARCHAR(255) do banco
        chunk_silver['cod_orgao_superior'] = chunk_silver['cod_orgao_superior'].astype(str).str.slice(0, 255)
        chunk_silver['nome_orgao_superior'] = chunk_silver['nome_orgao_superior'].astype(str).str.slice(0, 255)
        chunk_silver['nome_viajante'] = chunk_silver['nome_viajante'].astype(str).str.slice(0, 255)
        chunk_silver['cargo'] = chunk_silver['cargo'].astype(str).str.slice(0, 255)
        
        # Mantém o corte dos campos longos TEXT
        chunk_silver['destinos'] = chunk_silver['destinos'].astype(str).str.slice(0, 4000)
        chunk_silver['motivo'] = chunk_silver['motivo'].astype(str).str.slice(0, 4000)
        
        linhas = [sanitizar_tupla(x) for x in chunk_silver.to_numpy()]
        banco.inserir_em_lote(conexao, sql_insert, linhas)
        
    cursor.close()
    print("Sucesso! Camada silver_viagem alimentada.")


def transformar_passagens(conexao):
    print("Processando e transformando: raw_passagem -> silver_passagem...")
    banco.executar(conexao, "SET FOREIGN_KEY_CHECKS = 0;")
    banco.executar(conexao, "TRUNCATE TABLE silver_passagem;")
    banco.executar(conexao, "SET FOREIGN_KEY_CHECKS = 1;")

    cursor = conexao.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT * FROM raw_passagem")
    
    colunas_silver = [
        'id_viagem', 'meio_transporte', 'pais_origem_ida', 'uf_origem_ida', 
        'cidade_origem_ida', 'pais_destino_ida', 'uf_destino_ida', 'cidade_destino_ida', 
        'valor_passagem', 'taxa_servico', 'data_emissao'
    ]
    placeholders = ", ".join(["%s"] * len(colunas_silver))
    sql_insert = f"INSERT INTO silver_passagem ({', '.join(colunas_silver)}) VALUES ({placeholders})"

    while True:
        linhas_raw = cursor.fetchmany(TAMANHO_BLOCO)
        if not linhas_raw:
            break
            
        chunk = pd.DataFrame(linhas_raw)
        chunk = chunk.replace(r'^\s*$', np.nan, regex=True).replace('None', np.nan)
        
        chunk['data_emissao'] = pd.to_datetime(chunk['data_emissao'], format='%d/%m/%Y', errors='coerce').dt.date
        
        for col in ['valor_passagem', 'taxa_servico']:
            chunk[col] = chunk[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            chunk[col] = pd.to_numeric(chunk[col], errors='coerce').fillna(0.00)
            chunk[col] = chunk[col].apply(lambda x: x if x >= 0 else 0.00)
            
        chunk_silver = chunk[chunk['id_viagem'].notna()][colunas_silver].copy()
        
        # SOLUÇÃO DEFINITIVA: Sanitização na conversão para tuplas usando Python Puro
        linhas = [sanitizar_tupla(x) for x in chunk_silver.to_numpy()]
        banco.inserir_em_lote(conexao, sql_insert, linhas)
        
    cursor.close()
    print("Sucesso! Camada silver_passagem alimentada.")


def transformar_pagamentos(conexao):
    print("Processando e transformando: raw_pagamento -> silver_pagamento...")
    banco.executar(conexao, "SET FOREIGN_KEY_CHECKS = 0;")
    banco.executar(conexao, "TRUNCATE TABLE silver_pagamento;")
    banco.executar(conexao, "SET FOREIGN_KEY_CHECKS = 1;")

    cursor = conexao.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT * FROM raw_pagamento")
    
    colunas_silver = [
        'id_viagem', 'num_proposta', 'nome_orgao_pagador', 'nome_ug_pagadora', 
        'tipo_pagamento', 'valor'
    ]
    placeholders = ", ".join(["%s"] * len(colunas_silver))
    sql_insert = f"INSERT INTO silver_pagamento ({', '.join(colunas_silver)}) VALUES ({placeholders})"

    while True:
        linhas_raw = cursor.fetchmany(TAMANHO_BLOCO)
        if not linhas_raw:
            break
            
        chunk = pd.DataFrame(linhas_raw)
        chunk = chunk.replace(r'^\s*$', np.nan, regex=True).replace('None', np.nan)
        
        chunk['valor'] = chunk['valor'].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        chunk['valor'] = pd.to_numeric(chunk['valor'], errors='coerce').fillna(0.00)
        chunk['valor'] = chunk['valor'].apply(lambda x: x if x >= 0 else 0.00)
        chunk['tipo_pagamento'] = chunk['tipo_pagamento'].fillna("NÃO INFORMADO")
        
        chunk_silver = chunk[chunk['id_viagem'].notna()][colunas_silver].copy()
        
        # SOLUÇÃO DEFINITIVA: Sanitização na conversão para tuplas usando Python Puro
        linhas = [sanitizar_tupla(x) for x in chunk_silver.to_numpy()]
        banco.inserir_em_lote(conexao, sql_insert, linhas)
        
    cursor.close()
    print("Sucesso! Camada silver_pagamento alimentada.")


def transformar_trechos(conexao):
    print("Processando e transformando: raw_trecho -> silver_trecho...")
    banco.executar(conexao, "SET FOREIGN_KEY_CHECKS = 0;")
    banco.executar(conexao, "TRUNCATE TABLE silver_trecho;")
    banco.executar(conexao, "SET FOREIGN_KEY_CHECKS = 1;")

    cursor = conexao.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT * FROM raw_trecho")
    
    colunas_silver = [
        'id_viagem', 'sequencia_trecho', 'origem_data', 'origem_uf', 
        'origem_cidade', 'destino_data', 'destino_uf', 'destino_cidade', 
        'meio_transporte', 'numero_diarias'
    ]
    
    # CORREÇÃO CRÍTICA: Mudamos de 'INSERT INTO' para 'INSERT IGNORE INTO'.
    # Se houver duplicidade entre chunks diferentes, o MySQL descarta a cópia silenciosamente sem falhar o pipeline.
    placeholders = ", ".join(["%s"] * len(colunas_silver))
    sql_insert = f"INSERT IGNORE INTO silver_trecho ({', '.join(colunas_silver)}) VALUES ({placeholders})"

    while True:
        linhas_raw = cursor.fetchmany(TAMANHO_BLOCO)
        if not linhas_raw:
            break
            
        chunk = pd.DataFrame(linhas_raw)
        chunk = chunk.replace(r'^\s*$', np.nan, regex=True).replace('None', np.nan)
        
        chunk['origem_data'] = pd.to_datetime(chunk['origem_data'], format='%d/%m/%Y', errors='coerce').dt.date
        chunk['destino_data'] = pd.to_datetime(chunk['destino_data'], format='%d/%m/%Y', errors='coerce').dt.date
        
        chunk['numero_diarias'] = chunk['numero_diarias'].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        chunk['numero_diarias'] = pd.to_numeric(chunk['numero_diarias'], errors='coerce').fillna(0.0)
        chunk['numero_diarias'] = chunk['numero_diarias'].apply(lambda x: x if x >= 0 else 0.0)
        
        chunk['sequencia_trecho'] = pd.to_numeric(chunk['sequencia_trecho'], errors='coerce').fillna(1).astype(int)
        chunk = chunk.drop_duplicates(subset=['id_viagem', 'sequencia_trecho'])
        
        chunk_silver = chunk[chunk['id_viagem'].notna()][colunas_silver].copy()
        
        # Sanitização para garantir compatibilidade com tipos do MySQL
        linhas = [sanitizar_tupla(x) for x in chunk_silver.to_numpy()]
        banco.inserir_em_lote(conexao, sql_insert, linhas)
        
    cursor.close()
    print("Sucesso! Camada silver_trecho alimentada.")


def main():
    try:
        print("Iniciando a Fase 2: Transformação de Dados (Camada Silver)...")
        conexao = banco.conectar()
        
        transformar_viagens(conexao)
        transformar_passagens(conexao)
        transformar_pagamentos(conexao)
        transformar_trechos(conexao)
        
        conexao.close()
        print("\n=== FASE 2: TRANSFORMAÇÃO E CAMADA SILVER CONCLUÍDA COM SUCESSO ===")
    except Exception as e:
        print(f"\nA execução do pipeline falhou na Fase 2: {e}")


if __name__ == "__main__":
    main()