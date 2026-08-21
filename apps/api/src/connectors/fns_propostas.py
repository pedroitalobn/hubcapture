"""Propostas do FNS — captação pelo ConsultaFNS, proposta a proposta.

O connector `fns` entrega os REPASSES (agregados por tipo × exercício, para a
lente de recebidos). Este entrega as PROPOSTAS individuais — o que o gestor
abre no painel esperando nº da proposta, tipo, portaria, empenho e o que falta
pagar. São dois produtos da MESMA API, com granularidades diferentes.

O contrato tem três degraus (lidos do fonte da SPA, §30b):

  1. `proposta/consultar?sgUf&coMunicipioIbge&ano` → AGREGADOS por tipo
     (CUSTEIO MAC, EQUIPAMENTO…) — daqui sai a lista de tipos com registro;
  2. o MESMO endpoint com `tpProposta=<tipo>` → as linhas INDIVIDUAIS, cada
     uma com `nuProposta` (é o drill que a SPA faz ao clicar no tipo);
  3. `proposta/obter-proposta?nuProposta=` → o DETALHE: nº e data da PORTARIA,
     `vlEmpenhado`, `vlPago`, `vlPagar`, situação por extenso ("Proposta
     Paga"), OBs de pagamento e parlamentares. É o que preenche o cabeçalho.

Mesmas pegadinhas do módulo (§30b): IBGE de 6 dígitos, `sgUf` obrigatório,
resposta em `{"resultado": {"itensPagina": …}}`. Datas do detalhe vêm em epoch
de MILISSEGUNDOS. O host bloqueia o IP deste servidor — tudo passa pelo
`_http.get_json`, que cai no egresso (§`_egress`).

CUSTO: cada proposta nova custa uma chamada de detalhe no egresso. O teto
`MAX_DETALHES` protege a rodada; o registro sem detalhe ainda entra (nº, tipo
e valores vêm do drill) e o detalhe chega na coleta seguinte.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from typing import Any

from ..core.config import settings
from ..services import config as config_service
from ..services import municipios as municipios_service
from ._http import ConnectorClientError, get_json
from .base import RawRecord, register

log = logging.getLogger(__name__)

SOURCE_ID = "fns_propostas"

ENDPOINT_CONSULTA = "proposta/consultar"
ENDPOINT_DETALHE = "proposta/obter-proposta"

PAGE = 50
MAX_PAGINAS = 20
MAX_ANOS = 3
#: detalhes (obter-proposta) por coleta — cada um é uma chamada de egresso
MAX_DETALHES = 120
#: pausa entre chamadas de detalhe (o egresso remoto tem limite de taxa)
PAUSA_DETALHE_S = 1.2


def _epoch_ms_para_data(v: Any) -> str | None:
    """1776394800000 → "2026-04-17" (a fonte manda epoch em ms)."""
    try:
        ms = int(v)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).date().isoformat()


def formatar_nu_proposta(nu: str) -> str:
    """"63000728013202600" → "63000.728013/2026-00" — como a fonte exibe.

    O nº cru é ilegível e não é o que o gestor digita no portal. Padrão NUP:
    5 (órgão) + 6 (sequencial) + 4 (ano) + 2 (dígito).
    """
    nu = str(nu or "").strip()
    if len(nu) == 17 and nu.isdigit():
        return f"{nu[:5]}.{nu[5:11]}/{nu[11:15]}-{nu[15:]}"
    return nu


class FnsPropostasConnector:
    source_id = SOURCE_ID

    def __init__(self, api_url: str | None = None) -> None:
        self.api_url = api_url or settings.fns_api_url

    async def _base(self) -> str:
        return await config_service.resolver("fns_api_url") or self.api_url

    async def _pagina(
        self, base: str, params: dict[str, str]
    ) -> tuple[list[dict], int]:
        data = await get_json(base, ENDPOINT_CONSULTA, params)
        r = data.get("resultado") if isinstance(data, dict) else None
        if not isinstance(r, dict):
            return [], 0
        itens = [x for x in (r.get("itensPagina") or []) if isinstance(x, dict)]
        return itens, int(r.get("totalPaginas") or 0)

    async def _consultar(self, base: str, filtro: dict[str, str]) -> list[dict]:
        saida: list[dict] = []
        pagina = 1
        while pagina <= MAX_PAGINAS:
            itens, total_paginas = await self._pagina(
                base, {**filtro, "page": str(pagina), "count": str(PAGE)}
            )
            await asyncio.sleep(PAUSA_DETALHE_S)  # cada página é uma chamada de egresso
            saida.extend(itens)
            if not itens or pagina >= (total_paginas or 1):
                break
            pagina += 1
        return saida

    async def _detalhe(self, base: str, nu_proposta: str) -> dict | None:
        try:
            data = await get_json(base, ENDPOINT_DETALHE, {"nuProposta": nu_proposta})
        except Exception:  # noqa: BLE001 — detalhe é enriquecimento, não bloqueio
            return None
        r = data.get("resultado") if isinstance(data, dict) else None
        return r if isinstance(r, dict) else None

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await self._base()
        uf = municipios_service.uf_do_ibge(municipio_ibge) or ""
        anos = [str(a) for a in range(since.year, date.today().year + 1)][-MAX_ANOS:]

        records: list[RawRecord] = []
        detalhes_restantes = MAX_DETALHES
        for ano in anos:
            comum = {"sgUf": uf, "coMunicipioIbge": municipio_ibge[:6], "ano": ano}
            # degrau 1: os TIPOS com registro no exercício
            agregados = await self._consultar(base, comum)
            tipos = sorted(
                {str(a.get("coTipoProposta") or "").strip() for a in agregados if a}
                - {""}
            )
            for tipo in tipos:
                # degrau 2: as propostas individuais do tipo
                linhas = await self._consultar(base, {**comum, "tpProposta": tipo})
                for linha in linhas:
                    nu = str(linha.get("nuProposta") or "").strip()
                    if not nu:
                        continue  # linha ainda agregada não é proposta
                    # degrau 3: o detalhe (portaria/empenho/situação)
                    detalhe = None
                    if detalhes_restantes > 0:
                        detalhe = await self._detalhe(base, nu)
                        detalhes_restantes -= 1
                        await asyncio.sleep(PAUSA_DETALHE_S)
                    fonte_row = {**linha, **(detalhe or {})}
                    situacao = (
                        (fonte_row.get("situacao") or {}).get(
                            "descricaoSituacaoproposta"
                        )
                        if isinstance(fonte_row.get("situacao"), dict)
                        else fonte_row.get("situacao")
                    )
                    # chaves canônicas que o normalizador (§35) reconhece; o
                    # registro-fonte inteiro segue por baixo, com o detalhe
                    # As chaves canônicas vão DENTRO do plano — é dele que o
                    # normalizador monta título, valores e a `execucao`
                    # (_EXEC_KEYS); o registro-fonte inteiro fica em `csv`,
                    # a retaguarda de todo campo (§46), com portaria e OBs.
                    plano = {
                        "numero_proposta": formatar_nu_proposta(nu),
                        "nome": f"{tipo} — {fonte_row.get('noEntidade') or 'FNS'}",
                        "objeto": (
                            f"{tipo} · {fonte_row.get('dsTipoRecurso') or ''} · "
                            f"{fonte_row.get('noEntidade') or ''}"
                        ).strip(" ·"),
                        "nome_orgao_superior": "Ministério da Saúde — FNS",
                        "modalidade": fonte_row.get("dsTipoRecurso") or "FNS",
                        "situacao": situacao,
                        # _EXEC_KEYS: viram execucao.{valor_global, valor_empenhado,
                        # valor_pago, ano} — os cards do cabeçalho do detalhe
                        "valor_total": fonte_row.get("vlProposta"),
                        "vl_global": fonte_row.get("vlProposta"),
                        "vl_empenhado": fonte_row.get("vlEmpenhado"),
                        "vl_pago": fonte_row.get("vlPago"),
                        "ano": int(ano),
                        "ano_prop": fonte_row.get("nuAnoProposta") or ano,
                        # nº e data da PORTARIA em claro no registro-fonte
                        "numero_portaria": fonte_row.get("nuPortaria"),
                        "data_portaria": _epoch_ms_para_data(fonte_row.get("dtPortaria")),
                        "valor_a_pagar": fonte_row.get("vlPagar"),
                        "csv": fonte_row,  # a linha bruta é retaguarda (§46)
                    }
                    records.append(
                        RawRecord(
                            source_id=SOURCE_ID,
                            id_externo=nu,
                            municipio_ibge=municipio_ibge,
                            raw={"plano_acao": {k: v for k, v in plano.items() if v is not None}},
                            endpoint=ENDPOINT_CONSULTA,
                        )
                    )
        if not records and not anos:
            raise ConnectorClientError("janela de coleta vazia")
        return records

    async def health_check(self) -> bool:
        try:
            data = await get_json(
                await self._base(), "repasse-dia/recuperar-data-ultimo-pagamento", {}
            )
            return bool(isinstance(data, dict) and data.get("resultado"))
        except Exception:  # noqa: BLE001
            return False


register(FnsPropostasConnector())
