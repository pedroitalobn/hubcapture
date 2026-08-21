"""Pacote de dados abertos do SIconv — download dos CSVs nacionais.

O TransfereGov publica o SIconv (transferências discricionárias e legais) como
um conjunto de ZIPs nacionais, um por TABELA do modelo de dados oficial:
`emenda`, `proposta`, `convenio`, `empenho`, `pagamento`… Cada ZIP carrega um
CSV `;` em UTF-8 com BOM.

Diferente dos demais connectors, aqui NÃO se coleta por município: baixa-se o
arquivo inteiro e o recorte acontece no banco. É o join `emenda.ID_PROPOSTA →
proposta.ID_PROPOSTA` que carimba o `COD_MUNIC_IBGE` — a chave canônica do Hub
(§4). A tabela `emenda` sozinha não sabe de que município é o dinheiro, e a
`apoiadores_emendas_programas` nem chega à proposta (só tem FK para `programa`).

O NOME do ZIP não é adivinhável com segurança: o repo já usa
`siconv_proposta.zip`, mas nem toda tabela segue esse prefixo. Por isso o nome é
RESOLVIDO em runtime, testando candidatos, com override no painel admin — §27
(rota chutada foi exatamente o que quebrou em produção).

Tudo em DISCO, nunca em memória: `proposta.csv` passa de 1 GB descompactado e
carregá-lo em RAM derrubaria o worker.

DUAS ORIGENS, nesta ordem (§27). A oficial do TransfereGov é a mais FRESCA, mas
responde **403 com desafio da Cloudflare** para o IP deste servidor (ver
`_egress`) — e desafio não se resolve com header nem com browser: o egresso
alternativo serve JSON de API, não ZIP de centenas de MB. O mesmo pacote está
espelhado em `repositorio.dados.gov.br/seges/detru/`, que responde 200 direto
daqui. Por isso a origem oficial continua sendo tentada primeiro (quando o
bloqueio cair, volta sozinha) e o espelho entra como retaguarda.

Os dois publicam com NOMES DIFERENTES para o mesmo arquivo — origem
`siconv_emenda.zip`, espelho `siconv_emenda.csv.zip` — daí a lista de
candidatos por tabela. O espelho carrega `data_carga_siconv.txt` com a data do
dump: é ela que o painel mostra, para ninguém ler dado de um mês atrás como se
fosse de hoje.
"""

from __future__ import annotations

import asyncio
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ..services import config as config_service

log = logging.getLogger(__name__)

SOURCE_ID = "siconv"

BASE_PADRAO = "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/"
#: espelho oficial no repositório de dados abertos — não passa por Cloudflare
BASE_ESPELHO = "https://repositorio.dados.gov.br/seges/detru/"
#: arquivo de metadado do espelho com a data do dump (dd/mm/aaaa hh:mm:ss)
ARQUIVO_DATA_CARGA = "data_carga_siconv.txt"

# Timeout generoso: são centenas de MB por arquivo. `connect` curto para falha
# de rede aparecer rápido; `read` alto porque o corpo demora mesmo.
TIMEOUT = httpx.Timeout(600.0, connect=15.0)
CHUNK = 1 << 20  # 1 MiB por vez no streaming
TENTATIVAS = 3


@dataclass(frozen=True)
class Arquivo:
    """Uma tabela do modelo de dados do SIconv publicada como ZIP."""

    tabela: str
    descricao: str
    # Candidatos de nome, em ordem. O primeiro que responder 200 vence.
    candidatos: tuple[str, ...] = field(default=())
    # Entra no pipeline de carga? As tabelas de execução já estão mapeadas aqui
    # (o modelo oficial as liga por NR_CONVENIO), mas ainda não têm destino no
    # schema do Hub — baixar centenas de MB sem uso seria desperdício.
    carrega: bool = False

    def nomes(self) -> tuple[str, ...]:
        # `*.csv.zip` primeiro: é como o espelho publica, e a origem responde
        # 404 rápido no que não existe — 404 custa menos que um download errado.
        return self.candidatos or (
            f"siconv_{self.tabela}.csv.zip",
            f"siconv_{self.tabela}.zip",
            f"{self.tabela}.csv.zip",
            f"{self.tabela}.zip",
        )


# Catálogo do pacote. Ligar uma tabela nova = mais uma entrada aqui; o
# downloader não muda. `carrega=True` = tem destino no schema do Hub hoje; as
# demais estão mapeadas para o admin poder baixá-las e conferir a fonte, mas
# não entram na carga (baixar centenas de MB sem destino é desperdício).
ARQUIVOS: dict[str, Arquivo] = {
    "emenda": Arquivo(
        "emenda",
        "Emenda parlamentar da proposta (NR_EMENDA, autor, tipo, valores)",
        carrega=True,
    ),
    "proposta": Arquivo(
        "proposta",
        "Proposta (COD_MUNIC_IBGE, NR_PROPOSTA, ANO_PROP, objeto, valores)",
        carrega=True,
    ),
    # Cadeia de execução: proposta → convenio → empenho. O convênio é a PONTE
    # (é ele que tem `ID_PROPOSTA` e `NR_CONVENIO`); o empenho só conhece o
    # número do convênio, então sem ele não há como dizer de que município é.
    "convenio": Arquivo(
        "convenio",
        "Convênio celebrado — ponte proposta↔empenho (e os agregados do convênio)",
        carrega=True,
    ),
    "empenho": Arquivo(
        "empenho",
        "Empenhos por convênio (inclui DESCRICAO_EMENDA_SIAFI)",
        carrega=True,
    ),
    # `pagamento`/`desembolso` são por CONVÊNIO, não por empenho: atribuir um
    # pagamento a um empenho específico exigiria `empenho_desembolso`, que é
    # mais um arquivo. Enquanto `proposta_empenhos.valor_pago` não tiver origem
    # confiável, ele fica NULL — melhor vazio que um número que não é daquele
    # documento.
    "pagamento": Arquivo("pagamento", "Pagamentos por convênio"),
    "desembolso": Arquivo("desembolso", "Desembolsos por convênio"),
    "empenho_desembolso": Arquivo(
        "empenho_desembolso",
        "De-para empenho↔desembolso — o elo que falta para o pago POR EMPENHO",
    ),
    "programa": Arquivo("programa", "Programas do órgão concedente (o que se pode captar)"),
    "programa_proposta": Arquivo(
        "programa_proposta", "De-para programa↔proposta (a qual programa a proposta concorre)"
    ),
    "proponentes": Arquivo("proponentes", "Proponentes cadastrados (CNPJ, natureza jurídica)"),
    "plano_aplicacao_detalhado": Arquivo(
        "plano_aplicacao_detalhado", "Plano de aplicação detalhado do convênio"
    ),
    "meta_crono_fisico": Arquivo("meta_crono_fisico", "Metas do cronograma físico"),
    "etapa_crono_fisico": Arquivo("etapa_crono_fisico", "Etapas das metas do cronograma físico"),
    "cronograma_desembolso": Arquivo("cronograma_desembolso", "Cronograma de desembolso"),
    "termo_aditivo": Arquivo("termo_aditivo", "Termos aditivos do convênio"),
    "prorroga_oficio": Arquivo("prorroga_oficio", "Prorrogas de ofício"),
    "historico_situacao": Arquivo(
        "historico_situacao", "Histórico de situação da proposta/convênio (tramitação)"
    ),
    "obtv": Arquivo("obtv", "Ordem bancária de transferência voluntária"),
    "ingresso_contrapartida": Arquivo("ingresso_contrapartida", "Ingressos de contrapartida"),
    "licitacao": Arquivo("licitacao", "Processos licitatórios do convênio"),
    "obra": Arquivo("obra", "Obras vinculadas ao convênio"),
    "apoiadores_emendas_programas": Arquivo(
        "apoiadores_emendas_programas",
        "Apoiadores da emenda (complemento — NÃO liga à proposta)",
    ),
}

# Tabelas que o job carrega hoje, na ordem em que fazem sentido.
CARREGADAS: tuple[str, ...] = tuple(t for t, a in ARQUIVOS.items() if a.carrega)


class DownloadError(RuntimeError):
    """Falha de download/extração — vira incidente em `sync_runs`, nunca silêncio."""


class _Bloqueado(RuntimeError):
    """A base recusou o IP deste servidor (desafio de bot) — tenta a próxima."""


async def base_url() -> str:
    """A base PREFERIDA — painel admin sobrescreve o padrão (§16)."""
    return (await config_service.resolver("siconv_downloads_url")) or BASE_PADRAO


async def bases() -> tuple[str, ...]:
    """Bases a tentar, em ordem. Override do painel VENCE e vira a única.

    Deixar o espelho como retaguarda automática de um override manual mascararia
    o override: o admin apontou para um lugar e receberia dado de outro.
    """
    override = await config_service.resolver("siconv_downloads_url")
    if override:
        return (override,)
    return (BASE_PADRAO, BASE_ESPELHO)


async def data_carga(base: str | None = None) -> str | None:
    """Data do dump publicada pela fonte (`data_carga_siconv.txt`), se houver.

    Só o espelho publica. Devolve o texto cru (dd/mm/aaaa hh:mm:ss) — quem
    exibe decide o formato; `None` = a base não informa.
    """
    raiz = base or BASE_ESPELHO
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=True
        ) as client:
            resp = await client.get(_url(raiz, ARQUIVO_DATA_CARGA))
        if resp.status_code >= 400:
            return None
        return resp.text.strip().lstrip("\ufeff") or None
    except Exception:  # noqa: BLE001 — metadado ausente não derruba a carga
        return None


def _url(base: str, nome: str) -> str:
    return f"{base.rstrip('/')}/{nome}"


async def _baixar_para(client: httpx.AsyncClient, url: str, destino: Path) -> bool:
    """Stream do corpo direto para o disco. `False` = 404 (candidato errado)."""
    async with client.stream("GET", url) as resp:
        if resp.status_code == 404:
            return False
        if resp.status_code in (403, 503) and (
            resp.headers.get("cf-mitigated") or "text/html" in resp.headers.get("content-type", "")
        ):
            raise _Bloqueado(f"{resp.status_code} — a origem recusa o IP deste servidor")
        resp.raise_for_status()
        with destino.open("wb") as saida:
            async for pedaco in resp.aiter_bytes(CHUNK):
                saida.write(pedaco)
    return True


def _extrair_csv(zip_path: Path, destino_dir: Path) -> Path:
    """Extrai o primeiro .csv do ZIP. Síncrono — o chamador põe em thread."""
    with zipfile.ZipFile(zip_path) as z:
        nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not nomes:
            raise DownloadError(f"{zip_path.name} não contém CSV (tem: {z.namelist()[:5]})")
        nome = nomes[0]
        # `extract` preserva caminho interno; queremos o arquivo solto e com
        # nome previsível para o COPY não depender da árvore do ZIP.
        alvo = destino_dir / Path(nome).name
        with z.open(nome) as origem, alvo.open("wb") as saida:
            while pedaco := origem.read(CHUNK):
                saida.write(pedaco)
    return alvo


async def baixar_csv(tabela: str, destino_dir: Path, base: str | None = None) -> Path:
    """Baixa o ZIP da tabela e devolve o caminho do CSV extraído.

    Percorre BASES × CANDIDATOS: a origem oficial primeiro, o espelho depois;
    em cada base, os nomes possíveis do arquivo. 404 e desafio da Cloudflare
    são respostas DEFINITIVAS (não adianta repetir) — 404 pula para o próximo
    nome, desafio abandona a base inteira, que é onde ele vale. Override manual
    do painel (`siconv_<tabela>_arquivo`) vence a lista de nomes.
    """
    arquivo = ARQUIVOS.get(tabela)
    if arquivo is None:
        raise DownloadError(f"tabela desconhecida no catálogo do SIconv: {tabela}")

    destino_dir.mkdir(parents=True, exist_ok=True)
    raizes = (base,) if base else await bases()

    override = await config_service.resolver(f"siconv_{tabela}_arquivo")
    candidatos_nomes = (override.strip(),) if override else arquivo.nomes()

    zip_path = destino_dir / f"{tabela}.zip"
    erros: list[str] = []
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        for raiz in raizes:
            base_bloqueada = False
            for nome in candidatos_nomes:
                if base_bloqueada:
                    break  # o bloqueio é do HOST: nenhum outro nome vai responder
                url = _url(raiz, nome)
                for tentativa in range(1, TENTATIVAS + 1):
                    try:
                        if await _baixar_para(client, url, zip_path):
                            log.info(
                                "siconv: %s baixado de %s (%d bytes)",
                                tabela,
                                url,
                                zip_path.stat().st_size,
                            )
                            return await asyncio.to_thread(_extrair_csv, zip_path, destino_dir)
                        erros.append(f"{nome}: 404")
                        break  # 404 é resposta definitiva: próximo candidato
                    except _Bloqueado as exc:
                        erros.append(f"{raiz}: {exc}")
                        base_bloqueada = True
                        break
                    except httpx.HTTPError as exc:
                        erros.append(f"{nome} (tentativa {tentativa}): {exc}")
                        if tentativa == TENTATIVAS:
                            break
                        await asyncio.sleep(2**tentativa)

    raise DownloadError(
        f"não consegui baixar o pacote `{tabela}` — tentei "
        f"{', '.join(candidatos_nomes)} em {', '.join(raizes)}. "
        f"Detalhe: {'; '.join(erros[:6])}. "
        f"Calibre `siconv_downloads_url` / `siconv_{tabela}_arquivo` no painel admin (Fontes)."
    )


@dataclass(frozen=True)
class Disponibilidade:
    """O que o admin precisa saber ANTES de mandar baixar centenas de MB."""

    tabela: str
    descricao: str
    carrega: bool
    nome: str | None  # nome do ZIP que respondeu (None = nenhum candidato serviu)
    url: str | None
    disponivel: bool
    tamanho: int | None  # Content-Length, quando a fonte publica
    erro: str | None = None


async def candidatos(tabela: str) -> tuple[str, ...]:
    """Nomes de ZIP a tentar, na ordem: override do painel vence o catálogo."""
    arquivo = ARQUIVOS.get(tabela)
    if arquivo is None:
        raise DownloadError(f"tabela desconhecida no catálogo do SIconv: {tabela}")
    override = await config_service.resolver(f"siconv_{tabela}_arquivo")
    return (override.strip(),) if override else arquivo.nomes()


async def _sondar(client: httpx.AsyncClient, url: str) -> tuple[bool, int | None]:
    """HEAD no candidato. Alguns CDNs recusam HEAD — nesse caso, um GET com
    `Range` de 1 byte confirma a existência sem baixar o arquivo."""
    resp = await client.head(url)
    if resp.status_code == 404:
        return False, None
    if resp.status_code >= 400:
        resp = await client.get(url, headers={"Range": "bytes=0-0"})
        if resp.status_code == 404:
            return False, None
        resp.raise_for_status()
        bruto = resp.headers.get("content-range", "").rsplit("/", 1)[-1]
        return True, int(bruto) if bruto.isdigit() else None
    bruto = resp.headers.get("content-length")
    return True, int(bruto) if bruto and bruto.isdigit() else None


async def inspecionar(tabela: str, base: str | None = None) -> Disponibilidade:
    """Resolve onde o ZIP está e quanto pesa — sem baixar.

    É o que dá honestidade à tela: "a fonte publica este arquivo" é diferente de
    "tentei e deu erro", e diferente ainda de "o nome mudou". Varre BASES ×
    CANDIDATOS e devolve a PRIMEIRA combinação que responde, com a URL inteira
    — assim o admin vê de qual das duas origens aquele arquivo viria hoje.
    Nunca levanta: falha de rede vira `erro` no próprio registro.
    """
    arquivo = ARQUIVOS[tabela]
    raizes = (base,) if base else await bases()
    primeira_url = None
    try:
        nomes = await candidatos(tabela)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=True
        ) as client:
            for raiz in raizes:
                for nome in nomes:
                    url = _url(raiz, nome)
                    primeira_url = primeira_url or url
                    try:
                        existe, tamanho = await _sondar(client, url)
                    except Exception:  # noqa: BLE001 — base fora/bloqueada: próxima
                        break
                    if existe:
                        return Disponibilidade(
                            tabela, arquivo.descricao, arquivo.carrega, nome, url, True, tamanho
                        )
        return Disponibilidade(
            tabela,
            arquivo.descricao,
            arquivo.carrega,
            None,
            primeira_url,
            False,
            None,
            f"nenhum candidato respondeu ({', '.join(nomes)}) em {', '.join(raizes)}",
        )
    except Exception as exc:  # noqa: BLE001 — diagnóstico não levanta
        return Disponibilidade(
            tabela, arquivo.descricao, arquivo.carrega, None, None, False, None, str(exc)
        )


async def inspecionar_todos(tabelas: tuple[str, ...] | None = None) -> list[Disponibilidade]:
    """Sonda o catálogo inteiro em paralelo (uma requisição por tabela)."""
    alvos = tabelas or tuple(ARQUIVOS)
    return list(await asyncio.gather(*(inspecionar(t) for t in alvos)))


async def health_check() -> bool:
    """Saudável = ALGUMA das bases responde (não baixa nada).

    Origem bloqueada com espelho no ar é fonte SAUDÁVEL: a carga do dia acontece
    do mesmo jeito. Marcar como doente aqui pintaria de vermelho um pipeline que
    está funcionando.
    """
    for raiz in await bases():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=True) as c:
                resp = await c.head(raiz)
            if resp.status_code < 500 and not (
                resp.status_code in (403, 503) and resp.headers.get("cf-mitigated")
            ):
                return True
        except Exception:  # noqa: BLE001 — health nunca levanta
            continue
    return False
