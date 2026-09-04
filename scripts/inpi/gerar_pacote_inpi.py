#!/usr/bin/env python3
"""Monta a documentação técnica do Hub Capture e gera o resumo digital hash do INPI.

O INPI não recebe o código-fonte: recebe apenas o resumo digital hash (SHA-512) do
arquivo, que vai impresso no certificado. A guarda do arquivo é do TITULAR e é ela
que prova, em juízo, o que foi registrado — por isso o pacote aqui é DETERMINÍSTICO
e carimba o commit de origem: qualquer perito pode regerá-lo e conferir o hash.

Uso:
    python3 scripts/inpi/gerar_pacote_inpi.py            # monta o pacote e imprime o hash
    python3 scripts/inpi/gerar_pacote_inpi.py --verificar dist/inpi/<arquivo>.zip

Só usa a biblioteca padrão — não depende do ambiente do projeto.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

# --- O que entra na documentação técnica --------------------------------------
# "Os trechos do programa de computador e demais dados considerados suficientes
#  para identificação e caracterização da sua originalidade (código-fonte) serão
#  objeto do registro" (INPI). Entra o que é AUTORAL: código, schema, migrations,
# configuração de build. Fica de fora o que não é criação (dependências, binários,
# lockfiles) e qualquer coisa que cheire a segredo.

EXTENSOES = {
    ".py", ".pyi",                      # API FastAPI, connectors, jobs, IA
    ".ts", ".tsx", ".js", ".mjs", ".cjs",  # web Next.js
    ".sql",                             # schema e RLS
    ".css",                             # design system
    ".html",                            # templates
    ".sh",                              # entrypoints
    ".toml", ".ini", ".cfg",            # build/config
    ".yml", ".yaml",                    # compose, CI
    ".json",                            # config (lockfiles filtrados abaixo)
    ".mako",                            # template do Alembic
    ".md",                              # CLAUDE.md e docs de arquitetura
}

NOMES_EXATOS = {"Dockerfile", "docker-entrypoint.sh", "Makefile"}

# Nunca entram: não são criação intelectual, ou são risco de vazamento.
EXCLUIR_SUFIXOS = ("-lock.yaml", "-lock.json", ".lock")
EXCLUIR_NOMES = {"package-lock.json", "pnpm-lock.yaml", "uv.lock", "poetry.lock"}
EXCLUIR_PREFIXOS_NOME = (".env",)  # .env, .env.example, .env.local...

QUEBRA = b"\n"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def raiz_do_repo() -> Path:
    return Path(_git("rev-parse", "--show-toplevel", cwd=Path(__file__).resolve().parent))


def selecionar(raiz: Path) -> list[Path]:
    """Arquivos versionados que compõem a documentação técnica, em ordem estável."""
    versionados = _git("ls-files", cwd=raiz).splitlines()
    escolhidos: list[Path] = []
    for rel in versionados:
        caminho = Path(rel)
        nome = caminho.name
        if nome.startswith(EXCLUIR_PREFIXOS_NOME) or nome in EXCLUIR_NOMES:
            continue
        if nome.endswith(EXCLUIR_SUFIXOS):
            continue
        if nome in NOMES_EXATOS or caminho.suffix in EXTENSOES:
            if (raiz / caminho).is_file():
                escolhidos.append(caminho)
    return sorted(escolhidos, key=lambda p: p.as_posix())


def metadados(raiz: Path) -> dict[str, str]:
    return {
        "commit": _git("rev-parse", "HEAD", cwd=raiz),
        "data_commit": _git("log", "-1", "--format=%ad", "--date=iso-strict", cwd=raiz),
        "data_primeiro_commit": _git(
            "log", "--reverse", "--format=%ad", "--date=short", cwd=raiz
        ).splitlines()[0],
        "total_commits": _git("rev-list", "--count", "HEAD", cwd=raiz),
        "sujo": _git("status", "--porcelain", cwd=raiz),
    }


def _linguagens(arquivos: list[Path]) -> str:
    mapa = {
        ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript (TSX)",
        ".js": "JavaScript", ".mjs": "JavaScript", ".sql": "SQL",
        ".css": "CSS", ".html": "HTML", ".sh": "Shell script",
    }
    contagem: dict[str, int] = {}
    for a in arquivos:
        if (nome := mapa.get(a.suffix)) is not None:
            contagem[nome] = contagem.get(nome, 0) + 1
    ordenado = sorted(contagem.items(), key=lambda kv: -kv[1])
    return ", ".join(
        f"{ling} ({n} arquivo{'s' if n > 1 else ''})" for ling, n in ordenado
    )


def montar_identificacao(raiz: Path, arquivos: list[Path], meta: dict[str, str]) -> str:
    total_bytes = sum((raiz / a).stat().st_size for a in arquivos)
    total_linhas = 0
    for a in arquivos:
        total_linhas += (raiz / a).read_bytes().count(b"\n")
    return "\n".join(
        [
            "DOCUMENTAÇÃO TÉCNICA — REGISTRO DE PROGRAMA DE COMPUTADOR (INPI)",
            "=" * 70,
            "",
            "Título do programa .....: Hub Capture",
            "Descrição ..............: Plataforma web de concentração, curadoria e",
            "                          monitoramento de propostas, editais e repasses",
            "                          de recursos das plataformas de transferência",
            "                          voluntária do governo federal brasileiro.",
            "",
            f"Commit de referência ...: {meta['commit']}",
            f"Data do commit .........: {meta['data_commit']}",
            f"Primeiro commit ........: {meta['data_primeiro_commit']}",
            f"Commits no histórico ...: {meta['total_commits']}",
            "",
            f"Arquivos no pacote .....: {len(arquivos)}",
            f"Linhas de código .......: {total_linhas}",
            f"Bytes ..................: {total_bytes}",
            f"Linguagens .............: {_linguagens(arquivos)}",
            "",
            "-" * 70,
            "Este arquivo é a documentação técnica de que trata o art. 3º da Lei",
            "9.609/98. O INPI não a recebe: recebe apenas o resumo digital hash",
            "(SHA-512) deste pacote .zip, que consta do certificado de registro.",
            "A guarda e a integridade deste arquivo são do titular do direito.",
            "-" * 70,
        ]
    )


def montar_inventario(raiz: Path, arquivos: list[Path]) -> str:
    linhas = [
        "INVENTÁRIO DOS ARQUIVOS (SHA-256 individual)",
        "=" * 70,
        "",
        f"{'SHA-256':<64}  {'LINHAS':>7}  {'BYTES':>9}  CAMINHO",
    ]
    for a in arquivos:
        dados = (raiz / a).read_bytes()
        linhas.append(
            f"{hashlib.sha256(dados).hexdigest():<64}  "
            f"{dados.count(QUEBRA):>7}  "
            f"{len(dados):>9}  {a.as_posix()}"
        )
    return "\n".join(linhas) + "\n"


def escrever_zip(destino: Path, entradas: list[tuple[str, bytes]]) -> None:
    """ZIP determinístico: data fixa, permissões fixas, ordem estável, SEM compressão.

    Sem compressão de propósito. A saída do deflate pode variar entre versões de
    zlib, e aí o mesmo commit daria hashes diferentes em máquinas diferentes —
    justamente o que não pode acontecer numa prova de integridade. Armazenado, o
    pacote é byte a byte igual em qualquer máquina, e o custo é uns poucos MB.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w") as z:
        for nome, dados in entradas:
            info = zipfile.ZipInfo(nome, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            info.create_system = 3  # Unix
            z.writestr(info, dados)


def _curto(caminho: Path, raiz: Path) -> str:
    """Caminho relativo à raiz quando está dentro dela; absoluto caso contrário."""
    try:
        return caminho.relative_to(raiz).as_posix()
    except ValueError:
        return str(caminho)


def sha512(caminho: Path) -> str:
    h = hashlib.sha512()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verificar", metavar="ZIP", help="confere o hash de um pacote já gerado")
    p.add_argument("--saida", default="dist/inpi", help="diretório de saída")
    p.add_argument("--permitir-sujo", action="store_true",
                   help="gera mesmo com alterações não commitadas (não recomendado)")
    args = p.parse_args()

    raiz = raiz_do_repo()

    if args.verificar:
        alvo = Path(args.verificar)
        if not alvo.is_file():
            print(f"erro: arquivo não encontrado: {alvo}", file=sys.stderr)
            return 1
        print(f"Arquivo ....: {alvo}")
        print(f"Bytes ......: {alvo.stat().st_size}")
        print(f"SHA-512 ....: {sha512(alvo)}")
        return 0

    meta = metadados(raiz)
    if meta["sujo"] and not args.permitir_sujo:
        print(
            "erro: há alterações não commitadas. O pacote precisa apontar para um\n"
            "commit exato para ser reproduzível. Commite antes, ou use --permitir-sujo.",
            file=sys.stderr,
        )
        return 1

    arquivos = selecionar(raiz)
    if not arquivos:
        print("erro: nenhum arquivo selecionado", file=sys.stderr)
        return 1

    entradas: list[tuple[str, bytes]] = [
        ("00-IDENTIFICACAO.txt", montar_identificacao(raiz, arquivos, meta).encode()),
        ("01-INVENTARIO.txt", montar_inventario(raiz, arquivos).encode()),
    ]
    entradas += [
        (f"codigo-fonte/{a.as_posix()}", (raiz / a).read_bytes()) for a in arquivos
    ]

    carimbo = datetime.now(UTC).strftime("%Y%m%d")
    destino = raiz / args.saida / f"hubcapture-documentacao-tecnica-{carimbo}-{meta['commit'][:7]}.zip"
    escrever_zip(destino, entradas)

    resumo = sha512(destino)
    recibo = destino.with_suffix(".hash.txt")
    recibo.write_text(
        "\n".join(
            [
                "RESUMO DIGITAL HASH — para digitar no formulário e-Software do INPI",
                "=" * 70,
                "",
                f"Arquivo ..............: {destino.name}",
                f"Tamanho (bytes) ......: {destino.stat().st_size}",
                f"Arquivos no pacote ...: {len(entradas)}",
                f"Commit de referência .: {meta['commit']}",
                f"Gerado em ............: {datetime.now(UTC).isoformat(timespec='seconds')}",
                "",
                "Algoritmo ............: SHA-512",
                "Resumo digital hash ..: ",
                resumo,
                "",
                "-" * 70,
                "Cole o valor acima no campo 'Resumo digital hash' do e-Software e",
                "selecione o algoritmo SHA-512. GUARDE o .zip exatamente como está:",
                "abrir, renomear internamente ou recompactar MUDA o hash e invalida",
                "a prova. Faça ao menos duas cópias em mídias distintas.",
                "-" * 70,
                "",
            ]
        )
    )

    print(f"Pacote ......: {_curto(destino, raiz)}")
    print(f"Bytes .......: {destino.stat().st_size}")
    print(f"Arquivos ....: {len(entradas)}")
    print(f"Commit ......: {meta['commit']}")
    print("Algoritmo ...: SHA-512")
    print(f"Hash ........: {resumo}")
    print(f"Recibo ......: {_curto(recibo, raiz)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
