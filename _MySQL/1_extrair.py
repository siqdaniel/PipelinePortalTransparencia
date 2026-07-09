import os
import zipfile
import requests
import pandas as pd
from config import (
    PASTA_DADOS, 
    DRIVE_FILE_ID, 
    TAMANHO_BLOCO, 
    ARQUIVOS, 
    CSV_SEPARADOR, 
    CSV_ENCODING
)
import banco

def baixar_arquivo_drive(file_id, caminho_destino):
    """
    Baixa o arquivo zip do Google Drive utilizando a API pública de download.
    """
    print(f"Iniciando o download do arquivo ID: {file_id}")
    # URL de exportação/download direto para arquivos públicos do Google Drive
    url = f"https://docs.google.com/uc?export=download&id={file_id.split('?')[0]}"
    
    try:
        resposta = requests.get(url, stream=True)
        resposta.raise_for_status()
        
        # Cria a pasta de dados se não existir
        caminho_destino.parent.mkdir(parents=True, exist_ok=True)
        
        with open(caminho_destino, "wb") as f:
            for bloco in resposta.iter_content(chunk_size=8192):
                if bloco:
                    f.write(bloco)
        print(f"Download concluído com sucesso! Salvo em: {caminho_destino}")
    except Exception as e:
        raise RuntimeError(f"Falha ao baixar o arquivo do Google Drive: {e}")


def carregar_csv_para_raw(conexao, caminho_zip, nome_csv, tabela_raw):
    """
    Abre o CSV de dentro do ZIP, lê em blocos (chunks) utilizando o pandas
    e realiza a carga em lote na tabela RAW correspondente de forma idempotente.
    """
    print(f"Processando arquivo '{nome_csv}' para a tabela '{tabela_raw}'...")
    
    # 1. Garantir Idempotência: Limpa a tabela antes de inserir os novos dados
    banco.executar(conexao, f"TRUNCATE TABLE {tabela_raw}")
    
    try:
        with zipfile.ZipFile(caminho_zip, 'r') as z:
            # Verifica se o arquivo existe dentro do zip
            if nome_csv not in z.namelist():
                raise FileNotFoundError(f"Arquivo {nome_csv} não encontrado dentro do ZIP.")
                
            with z.open(nome_csv) as f:
                # O pandas lê o arquivo em pedaços (TextFileReader)
                leitor_blocos = pd.read_csv(
                    f,
                    sep=CSV_SEPARADOR,
                    encoding=CSV_ENCODING,
                    dtype=str,             # Força todas as colunas como string (Exigência da RAW)
                    chunksize=TAMANHO_BLOCO,
                    low_memory=False
                )
                
                total_linhas = 0
                for chunk in leitor_blocos:
                    # Substitui valores NaN/None por strings vazias para evitar quebras no banco
                    chunk = chunk.fillna("")
                    
                    # Converte o DataFrame do bloco em uma lista de tuplas
                    linhas = [tuple(x) for x in chunk.to_numpy()]
                    
                    if not linhas:
                        continue
                        
                    # Dinamiza os placeholders '%s' de acordo com o número de colunas do CSV
                    num_colunas = len(chunk.columns)
                    placeholders = ", ".join(["%s"] * num_colunas)
                    sql_insert = f"INSERT INTO {tabela_raw} VALUES ({placeholders})"
                    
                    # Inserção em lote usando a função do modulo banco.py
                    banco.inserir_em_lote(conexao, sql_insert, linhas)
                    total_linhas += len(linhas)
                    
                print(f"Sucesso! {total_linhas} linhas carregadas na tabela {tabela_raw}.")
                
    except Exception as e:
        print(f"ERRO ao processar o arquivo {nome_csv}: {e}")
        raise e


def main():
    # Definição do caminho do arquivo local
    caminho_zip = PASTA_DADOS / "viagens_2025_6meses.zip"
    
    # Passo 1: Download do arquivo
    try:
        # Se o arquivo já existir localmente e você não quiser baixar sempre, 
        # pode comentar a linha abaixo. Mas para o pipeline de produção automatizado:
        baixar_arquivo_drive(DRIVE_FILE_ID, caminho_zip)
    except Exception as e:
        print(f"Fase de Download falhou: {e}")
        return

    # Passo 2: Conexão com o banco e Carga RAW
    try:
        print("Conectando ao banco de dados...")
        conexao = banco.conectar()
        
        # Itera sobre o dicionário de mapeamento configurado no config.py
        for chave, info in ARQUIVOS.items():
            carregar_csv_para_raw(
                conexao=conexao,
                caminho_zip=caminho_zip,
                nome_csv=info["csv"],
                tabela_raw=info["tabela_raw"]
            )
            
        conexao.close()
        print("\n=== FASE 1: EXTRAÇÃO E CAMADA RAW CONCLUÍDA COM SUCESSO ===")
        
    except Exception as e:
        print(f"\nA execução do pipeline falhou na Fase 1: {e}")


if __name__ == "__main__":
    main()