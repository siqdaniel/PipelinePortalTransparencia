import os
import zipfile
import gdown
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
    Baixa arquivos do Google Drive utilizando a biblioteca gdown,
    contornando nativamente avisos de segurança para arquivos grandes.
    """
    print(f"Iniciando o download automatizado via gdown do ID: {file_id}")
    try:
        # Garante que a pasta de destino exista
        caminho_destino.parent.mkdir(parents=True, exist_ok=True)
        
        # O gdown aceita o ID diretamente e gerencia o download em blocos visualmente
        gdown.download(id=file_id, output=str(caminho_destino), quiet=False)
        
        print(f"Download concluído com sucesso! Salvo em: {caminho_destino}")
    except Exception as e:
        raise RuntimeError(f"Falha ao baixar o arquivo usando gdown: {e}")
def carregar_csv_para_raw(conexao, caminho_zip, nome_csv, tabela_raw):
    """
    Abre o CSV de dentro do ZIP, lê em blocos (chunks) utilizando o pandas
    e realiza a carga em lote na tabela RAW correspondente de forma idempotente.
    """
    print(f"Processando arquivo '{nome_csv}' para a tabela '{tabela_raw}'...")
    
    # Garantir Idempotência: Limpa a tabela antes de inserir os novos dados
    banco.executar(conexao, f"TRUNCATE TABLE {tabela_raw}")
    
    # Descobre quantas colunas a tabela física possui no MySQL
    cursor = conexao.cursor()
    cursor.execute(f"SELECT * FROM {tabela_raw} LIMIT 0")
    cursor.fetchall()
    num_colunas_banco = len(cursor.description)
    cursor.close()
    
    try:
        with zipfile.ZipFile(caminho_zip, 'r') as z:
            if nome_csv not in z.namelist():
                raise FileNotFoundError(f"Arquivo {nome_csv} não encontrado dentro do ZIP.")
                
            with z.open(nome_csv) as f:
                leitor_blocos = pd.read_csv(
                    f,
                    sep=CSV_SEPARADOR,
                    encoding=CSV_ENCODING,
                    dtype=str,             # Mantém os dados brutos como texto na camada Raw
                    chunksize=TAMANHO_BLOCO,
                    low_memory=False
                )
                
                total_linhas = 0
                # Monta a query fixa baseada no número de colunas real da tabela do banco
                placeholders = ", ".join(["%s"] * num_colunas_banco)
                sql_insert = f"INSERT INTO {tabela_raw} VALUES ({placeholders})"
                
                for chunk in leitor_blocos:
                    chunk = chunk.fillna("")
                    
                    linhas = []
                    for row in chunk.to_numpy():
                        # Converte a linha para lista para podermos manipular o tamanho
                        lista_valores = list(row)
                        
                        # Se a linha do CSV tiver mais colunas que o banco, corta o excesso
                        if len(lista_valores) > num_colunas_banco:
                            lista_valores = lista_valores[:num_colunas_banco]
                        # Se tiver menos colunas, preenche com strings vazias
                        elif len(lista_valores) < num_colunas_banco:
                            lista_valores.extend([""] * (num_colunas_banco - len(lista_valores)))
                            
                        linhas.append(tuple(lista_valores))
                    
                    if not linhas:
                        continue
                    
                    # Inserção em lote segura
                    banco.inserir_em_lote(conexao, sql_insert, linhas)
                    total_linhas += len(linhas)
                    
                print(f"Sucesso! {total_linhas} linhas carregadas na tabela {tabela_raw}.")
                
    except Exception as e:
        print(f"ERRO ao processar o arquivo {nome_csv}: {e}")
        raise 


def main():
    # Definição do caminho do arquivo local onde o zip será salvo
    caminho_zip = PASTA_DADOS / "viagens_2025_6meses.zip"
    
    # Passo 1: Download do arquivo via gdown (Atendendo ao requisito e dica da professora)
    try:
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