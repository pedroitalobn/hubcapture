"""Connector Emendas parlamentares (recebidos).

Emendas pagas ao município (por autor/comissão). Cada pagamento vira um RawRecord
de repasse com `emenda=True` e a área/categoria quando disponível.

IMPORTANTE: a API do Portal da Transparência EXIGE a chave `chave-api-dados`
(cadastro gratuito em portaldatransparencia.gov.br/api-de-dados). Sem a chave
(painel `emendas_api_key`), o connector falha com mensagem clara — registrada em
`sync_runs` — em vez de um 401 opaco.

Calibração real: o endpoint `/emendas` do Portal aceita `ano` e `pagina` —
NÃO filtra por município. O connector pagina o ano e refiltra no cliente por
`localidadeDoGasto` (nome do município resolvido via IBGE Localidades, com
comparação sem acento + UF). Sem conseguir resolver o nome, falha com mensagem
clara em vez de ingerir emendas de outros municípios.
"""

from __future__ import annotations

import unicodedata
from datetime import date

from ..core.config import settings
from ..services import config as config_service
from ..services import municipios as municipios_service
from ._http import ConnectorClientError, get_json
from .base import RawRecord, register

ENDPOINT = "emendas"
MAX_PAGINAS = 20  # limite defensivo de paginação por ano


def _norm(texto: str) -> str:
    sem = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").upper().strip()


def _da_localidade(row: dict, nome: str, uf: str) -> bool:
    """localidadeDoGasto vem como 'FORTALEZA - CE' (ou variações)."""
    local = _norm(str(row.get("localidadeDoGasto") or row.get("localidade") or ""))
    if not local:
        return False
    alvo = _norm(nome)
    if not local.startswith(alvo):
        return False
    resto = local[len(alvo) :]
    return (not uf) or (_norm(uf) in resto) or resto.strip(" -") == ""


class ChaveApiAusente(Exception):
    """Portal da Transparência exige `chave-api-dados` — configure no painel."""


class EmendasConnector:
    source_id = "emendas"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.emendas_base_url

    async def _headers(self) -> dict[str, str]:
        chave = await config_service.resolver("emendas_api_key")
        if not chave:
            raise ChaveApiAusente(
                "Configure emendas_api_key no painel admin (chave-api-dados do "
                "Portal da Transparência — cadastro gratuito)"
            )
        return {"chave-api-dados": chave}

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("emendas_base_url") or self.base_url
        headers = await self._headers()
        resolvido = await municipios_service.nome_uf_por_ibge(municipio_ibge)
        if resolvido is None:
            raise ConnectorClientError(
                f"não resolvi o nome do município {municipio_ibge} (IBGE "
                "Localidades indisponível) — a API de emendas só filtra por nome"
            )
        nome, uf = resolvido

        linhas: list[dict] = []
        for pagina in range(1, MAX_PAGINAS + 1):
            data = await get_json(
                base,
                ENDPOINT,
                {"ano": str(since.year), "pagina": str(pagina)},
                headers=headers,
            )
            lote = data.get("items", data) if isinstance(data, dict) else data
            if not isinstance(lote, list) or not lote:
                break
            linhas.extend(r for r in lote if isinstance(r, dict))
            if len(lote) < 10:  # última página (page size do Portal é >= 10)
                break

        do_municipio = [r for r in linhas if _da_localidade(r, nome, uf)]
        records: list[RawRecord] = []
        for row in do_municipio:
            id_ext = str(row.get("codigoEmenda") or row.get("id"))
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=id_ext,
                    municipio_ibge=municipio_ibge,
                    endpoint=ENDPOINT,
                    raw={
                        "data_repasse": row.get("dataPagamento"),
                        "descricao": row.get("objeto") or row.get("funcao"),
                        "categoria": row.get("funcao"),
                        "orgao_superior": row.get("orgao"),
                        "natureza": "repasse",
                        "valor": row.get("valorPago"),
                        "documento": row.get("numeroEmenda"),
                        "emenda": True,
                        "detalhe": {"autor": row.get("nomeAutor")},
                    },
                )
            )
        return records

    async def health_check(self) -> bool:
        try:
            await get_json(self.base_url, ENDPOINT, {"pagina": "1"}, headers=await self._headers())
            return True
        except Exception:
            return False


register(EmendasConnector())
