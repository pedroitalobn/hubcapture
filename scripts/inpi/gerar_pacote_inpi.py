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
    """Abertura do pacote: o que é o programa e o que nele é original.

    A documentação técnica serve para "identificar e caracterizar a
    originalidade" da criação (INPI). O código sozinho não faz isso: é o texto
    que diz ao perito o que, no meio de 100 mil linhas, é a criação — aqui, a
    leitura do PERFIL do gestor por IA e o acompanhamento que decorre dela.
    """
    total_bytes = sum((raiz / a).stat().st_size for a in arquivos)
    total_linhas = 0
    for a in arquivos:
        total_linhas += (raiz / a).read_bytes().count(QUEBRA)
    return "\n".join(
        [
            "DOCUMENTAÇÃO TÉCNICA — REGISTRO DE PROGRAMA DE COMPUTADOR (INPI)",
            "=" * 70,
            "",
            "Título do programa: Hub Capture",
            "",
            "",
            "1. DESCRIÇÃO",
            "-" * 70,
            "",
            "Plataforma web que concentra, organiza e monitora propostas, editais",
            "e repasses de recursos das plataformas de transferência voluntária do",
            "governo federal brasileiro (TransfereGov, Fundo Nacional de Saúde e",
            "FNDE), voltada ao gestor público municipal — prefeituras, secretarias,",
            "gabinetes parlamentares e suas equipes.",
            "",
            "O programa emprega INTELIGÊNCIA ARTIFICIAL para interpretar as DEMANDAS",
            "E NECESSIDADES do município e do gestor e, a partir dessa leitura do",
            "perfil, selecionar entre as oportunidades disponíveis as que são",
            "pertinentes àquele território e SUGERIR O ACOMPANHAMENTO das propostas",
            "correspondentes. À medida que a IA apura o entendimento do perfil — o",
            "município, as áreas de atuação, o papel do usuário e o que ele já",
            "acompanha —, a seleção e as sugestões de acompanhamento se ajustam.",
            "",
            "",
            "2. CARACTERÍSTICAS ORIGINAIS",
            "-" * 70,
            "",
            "O que distingue o programa das demais soluções de captação de recursos",
            "públicos disponíveis no mercado brasileiro:",
            "",
            "2.1. NAVEGAÇÃO A PARTIR DO PERFIL, NÃO DA FONTE DE DADOS",
            "     As soluções concorrentes organizam a interface por plataforma de",
            "     origem: uma aba para o TransfereGov, outra para o Fundo Nacional",
            "     de Saúde, outra para o FNDE — cabendo ao gestor percorrer fonte",
            "     por fonte e descobrir sozinho o que se aplica ao município dele.",
            "     Aqui a navegação parte do PERFIL: os municípios de interesse, as",
            "     áreas de atuação e o papel do usuário. As fontes são detalhe",
            "     interno de ingestão e não aparecem como divisão da interface; as",
            "     telas são recortes (lentes) sobre o território do gestor,",
            "     organizadas pelo ciclo do recurso — captar, receber, executar,",
            "     prestar contas.",
            "",
            "2.2. CADASTRO CONVERSACIONAL CONDUZIDO POR IA",
            "     O perfil não é coletado por formulário: um assistente conversa",
            "     com o gestor (papel, municípios, áreas de interesse, canais de",
            "     aviso), infere as fontes de dados pertinentes a partir das áreas",
            "     declaradas e dispara a primeira coleta dirigida ao território.",
            "",
            "2.3. CURADORIA AUTOMÁTICA EM DUAS CAMADAS",
            "     Cada proposta coletada é classificada em taxonomia fechada de",
            "     áreas temáticas e recebe resumo adaptado ao papel do usuário. A",
            "     primeira camada é determinística (sem rede e sem custo por",
            "     registro) e a segunda usa modelo de linguagem para refinar a",
            "     classificação e redigir o resumo. A classificação é também o",
            "     filtro do painel, de modo que a leitura da IA se converte",
            "     diretamente em recorte navegável.",
            "",
            "2.4. COPILOTO COM CHAMADA DE FERRAMENTAS SOBRE O PRÓPRIO SISTEMA",
            "     Assistente conversacional permanente que responde consultando as",
            "     funções do próprio programa (mais de vinte ferramentas: propostas,",
            "     prazos, repasses, empenhos, pareceres, emendas, obras, alertas,",
            "     agenda), sempre na mesma sessão de banco isolada por inquilino —",
            "     de modo que só enxerga o território daquele usuário. Além de",
            "     responder, executa ações reversíveis a pedido: marcar proposta",
            "     para acompanhamento, disparar varredura, dar baixa em avisos.",
            "",
            "2.5. ACOMPANHAMENTO SUGERIDO E VIGIADO POR CRITÉRIOS ESCOLHIDOS",
            "     A partir do perfil, o programa propõe o acompanhamento das",
            "     propostas pertinentes e passa a vigiá-las. O usuário escolhe QUE",
            "     fatos quer receber — parecer novo, alteração de parecer, empenho",
            "     emitido, pagamento, emenda aplicada, publicação, vencimento de",
            "     vigência, mudança de situação, prazo, pendência, proposta nova no",
            "     município. A detecção compara fotografias sucessivas do estado",
            "     material de cada proposta e emite um aviso por critério com fato",
            "     novo, em vez de um aviso genérico de alteração.",
            "",
            "2.6. COLETA COMBINADA COM FUSÃO POR PRECEDÊNCIA DE CAMPO",
            "     Para cada fonte, a consulta a interface de programação e a",
            "     extração automatizada das páginas públicas são executadas em",
            "     paralelo e os resultados são fundidos registro a registro, com",
            "     precedência declarada por campo (identificadores, valores e datas",
            "     prevalecem da interface programática; situação, pendências e",
            "     movimentação prevalecem da extração de página, por serem mais",
            "     atuais) e registro da origem de cada valor para auditoria.",
            "",
            "",
            "3. COMPOSIÇÃO DESTA DOCUMENTAÇÃO",
            "-" * 70,
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
