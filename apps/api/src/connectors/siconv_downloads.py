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

O NOME do ZIP quase sempre é `siconv_<tabela>.zip`, mas nem sempre:
`apoiadores_emendas_programas.zip` vai sem o prefixo. Por isso o nome é
RESOLVIDO em runtime, testando candidatos, com override no painel admin — §27
(rota chutada foi exatamente o que quebrou em produção). Os nomes das tabelas
que carregamos foram conferidos contra a página oficial de downloads.

Tudo em DISCO, nunca em memória: `proposta.csv` passa de 1 GB descompactado e
carregá-lo em RAM derrubaria o worker.
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
        return self.candidatos or (f"siconv_{self.tabela}.zip", f"{self.tabela}.zip")


# Catálogo. Ligar uma tabela nova = mais uma entrada aqui; o downloader não muda.
ARQUIVOS: dict[str, Arquivo] = {
    # Os tamanhos são a referência de custo diário do job (conferidos na página
    # oficial): as quatro carregadas somam ~245 MB comprimidos.
    "emenda": Arquivo(
        "emenda",
        "Emenda parlamentar da proposta (NR_EMENDA, autor, tipo, valores) — ~8 MB",
        carrega=True,
    ),
    "proposta": Arquivo(
        "proposta",
        "Proposta (COD_MUNIC_IBGE, NR_PROPOSTA, ANO_PROP, objeto, valores) — ~196 MB",
        carrega=True,
    ),
    # Cadeia de execução: proposta → convenio → empenho. O convênio é a PONTE
    # (é ele que tem `ID_PROPOSTA` e `NR_CONVENIO`); o empenho só conhece o
    # número do convênio, então sem ele não há como dizer de que município é.
    "convenio": Arquivo(
        "convenio",
        "Convênio celebrado — ponte proposta↔empenho (e os agregados) — ~18 MB",
        carrega=True,
    ),
    "empenho": Arquivo(
        "empenho",
        "Empenhos por convênio (inclui DESCRICAO_EMENDA_SIAFI) — ~22 MB",
        carrega=True,
    ),
    # `pagamento`/`desembolso` são por CONVÊNIO, não por empenho. `desembolso`
    # (~16 MB) + `empenho_desembolso` (~3 MB) fecham a atribuição por documento
    # e são baratos — é o próximo passo para `proposta_empenhos.valor_pago`
    # deixar de ser NULL. Enquanto não houver essa origem, ele fica vazio:
    # melhor nada que um rateio que não é daquele empenho.
    "desembolso": Arquivo("desembolso", "Desembolsos por convênio — ~16 MB"),
    "empenho_desembolso": Arquivo(
        "empenho_desembolso", "Elo empenho↔desembolso — destrava o pago por empenho (~3 MB)"
    ),
    "pagamento": Arquivo("pagamento", "Pagamentos por convênio — ~349 MB"),
    "apoiadores_emendas_programas": Arquivo(
        "apoiadores_emendas_programas",
        "Apoiadores da emenda (complemento — NÃO liga à proposta)",
        # publicado SEM o prefixo `siconv_`
        candidatos=("apoiadores_emendas_programas.zip",),
    ),
}

# Tabelas que o job carrega hoje, na ordem em que fazem sentido.
CARREGADAS: tuple[str, ...] = tuple(t for t, a in ARQUIVOS.items() if a.carrega)


class DownloadError(RuntimeError):
    """Falha de download/extração — vira incidente em `sync_runs`, nunca silêncio."""


async def base_url() -> str:
    """Base dos downloads: painel admin sobrescreve o padrão (§16)."""
    return (await config_service.resolver("siconv_downloads_url")) or BASE_PADRAO


def _url(base: str, nome: str) -> str:
    return f"{base.rstrip('/')}/{nome}"


async def _baixar_para(client: httpx.AsyncClient, url: str, destino: Path) -> bool:
    """Stream do corpo direto para o disco. `False` = 404 (candidato errado)."""
    async with client.stream("GET", url) as resp:
        if resp.status_code == 404:
            return False
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

    Resolve o nome do arquivo testando os candidatos (404 → próximo) e aceita
    override manual pelo painel (`siconv_<tabela>_arquivo`).
    """
    arquivo = ARQUIVOS.get(tabela)
    if arquivo is None:
        raise DownloadError(f"tabela desconhecida no catálogo do SIconv: {tabela}")

    destino_dir.mkdir(parents=True, exist_ok=True)
    raiz = base or await base_url()

    override = await config_service.resolver(f"siconv_{tabela}_arquivo")
    candidatos = (override.strip(),) if override else arquivo.nomes()

    zip_path = destino_dir / f"{tabela}.zip"
    erros: list[str] = []
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        for nome in candidatos:
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
                except httpx.HTTPError as exc:
                    erros.append(f"{nome} (tentativa {tentativa}): {exc}")
                    if tentativa == TENTATIVAS:
                        break
                    await asyncio.sleep(2**tentativa)

    raise DownloadError(
        f"não consegui baixar o pacote `{tabela}` de {raiz} — tentei "
        f"{', '.join(candidatos)}. Detalhe: {'; '.join(erros[:6])}. "
        f"Calibre `siconv_downloads_url` / `siconv_{tabela}_arquivo` no painel admin (Fontes)."
    )


async def health_check() -> bool:
    """Saudável = a base responde (não baixa nada; só confirma que está de pé)."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=True) as c:
            resp = await c.head(await base_url())
        return resp.status_code < 500
    except Exception:  # noqa: BLE001 — health nunca levanta
        return False
