"""Connector FPM — Fundo de Participação dos Municípios (recebidos).

Fonte: API de Transferências Constitucionais do Tesouro (ORDS,
apidatalake.tesouro.gov.br/ords/transferencias/). A rota exata não é fixa aqui:
o connector se AUTOCALIBRA —
  1. rota manual do painel admin (`fpm_endpoint`), se definida;
  2. descoberta via `metadata-catalog/` do ORDS (nome contendo 'transfer');
  3. candidatos conhecidos (tt/transferencias, transferencias…).
Os parâmetros também variam por implantação (cod_ibge/ano vs id_ente/
an_exercicio) → envia os dois estilos e SEMPRE refiltra no cliente pelo IBGE
(linha sem coluna de IBGE compatível é descartada — nunca ingere o Brasil
inteiro por engano).

Cada linha vira um RawRecord de repasse; deduções (FUNDEB/PASEP/retenções)
recebem `natureza='deducao'` para o dashboard calcular o líquido.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from ..core.config import settings
from ..services import config as config_service
from ._http import ConnectorClientError, get_json
from .base import RawRecord, register

ENDPOINT_CANDIDATES = (
    "tt/transferencias",
    "transferencias",
    "tt/transferencia",
    "tt/fpm",
)
PAGE_LIMIT = 500
_DEDUCAO_KWS = ("fundeb", "pasep", "reten", "deduc")

# cache da rota que funcionou, por base_url
_endpoint_cache: dict[str, str] = {}


def _digits(v: Any) -> str:
    return "".join(c for c in str(v) if c.isdigit())


def _linha_do_municipio(row: dict, ibge: str) -> bool:
    """Aceita a linha só se alguma coluna de IBGE/ente bater (7 ou 6 dígitos)."""
    for k, v in row.items():
        lk = k.lower()
        if "ibge" in lk or lk in ("id_ente", "cod_ente", "codigo_ente"):
            d = _digits(v)
            if d and (d == ibge or d == ibge[:6]):
                return True
    return False


def _campo(row: dict, *keywords: str) -> Any:
    for k, v in row.items():
        lk = k.lower()
        if any(kw in lk for kw in keywords):
            return v
    return None


def _montar_raw(row: dict) -> dict:
    """Mapeia uma linha do ORDS (schema variável) para o shape do normalizador."""
    descricao = _campo(row, "transferencia", "tipo", "fundo", "item", "descricao") or "FPM"
    valor = row.get("valor") or _campo(row, "valor", "vl_")
    data_repasse = _campo(row, "data", "dt_")
    if not data_repasse:
        ano = _campo(row, "ano", "exercicio")
        mes = _campo(row, "mes")
        if ano and mes and _digits(mes):
            data_repasse = f"{_digits(ano)}-{int(_digits(mes)):02d}-01"
    natureza = "deducao" if any(kw in str(descricao).lower() for kw in _DEDUCAO_KWS) else "credito"
    return {
        "data_repasse": data_repasse,
        "descricao": str(descricao),
        "categoria": "FPM",
        "orgao_superior": "Tesouro Nacional",
        "natureza": natureza,
        "valor": valor,
        "competencia": _campo(row, "decendio", "parcela", "competencia"),
        "detalhe": row,
    }


def _id_externo(row: dict, ibge: str) -> str:
    rid = row.get("id") or _campo(row, "id_transferencia")
    if rid:
        return str(rid)
    payload = json.dumps(row, sort_keys=True, default=str, ensure_ascii=False)
    return f"{ibge}:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


class FpmConnector:
    source_id = "fpm"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.fpm_base_url

    async def _rotas_candidatas(self, base: str) -> list[str]:
        override = await config_service.resolver("fpm_endpoint")
        if override:
            return [override]
        if base in _endpoint_cache:
            return [_endpoint_cache[base]]
        rotas: list[str] = []
        try:  # ORDS lista os serviços expostos em metadata-catalog/
            catalogo = await get_json(base, "metadata-catalog/", {})
            for item in catalogo.get("items", []) if isinstance(catalogo, dict) else []:
                nome = str(item.get("name") or "")
                if "transfer" in nome.lower() or "fpm" in nome.lower():
                    rotas.append(nome.strip("/"))
        except Exception:
            pass
        rotas.extend(r for r in ENDPOINT_CANDIDATES if r not in rotas)
        return rotas

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        base = await config_service.resolver("fpm_base_url") or self.base_url
        # os dois estilos de parâmetro conhecidos do ORDS do Tesouro; params
        # desconhecidos são ignorados pelo servidor e o refiltro local garante
        params = {
            "cod_ibge": municipio_ibge,
            "id_ente": municipio_ibge,
            "ano": str(since.year),
            "an_exercicio": str(since.year),
            "limit": str(PAGE_LIMIT),
        }
        ultima_falha: Exception | None = None
        for rota in await self._rotas_candidatas(base):
            try:
                data = await get_json(base, rota, params)
            except Exception as exc:  # 404/400 → tenta a próxima rota
                ultima_falha = exc
                continue
            linhas = data.get("items", data) if isinstance(data, dict) else data
            if not isinstance(linhas, list):
                continue
            do_municipio = [
                row
                for row in linhas
                if isinstance(row, dict) and _linha_do_municipio(row, municipio_ibge)
            ]
            if not do_municipio:
                # rota respondeu mas sem linha do município → pode ser rota errada
                ultima_falha = ConnectorClientError(
                    f"{rota}: nenhuma linha com IBGE {municipio_ibge}"
                )
                continue
            _endpoint_cache[base] = rota
            return [
                RawRecord(
                    source_id=self.source_id,
                    id_externo=_id_externo(row, municipio_ibge),
                    municipio_ibge=municipio_ibge,
                    endpoint=rota,
                    raw=_montar_raw(row),
                )
                for row in do_municipio
            ]
        raise ConnectorClientError(
            "nenhuma rota do ORDS do Tesouro respondeu com dados do município — "
            f"defina fpm_endpoint no painel admin. Última falha: {ultima_falha}"
        )

    async def health_check(self) -> bool:
        base = await config_service.resolver("fpm_base_url") or self.base_url
        try:
            await get_json(base, "metadata-catalog/", {})
            return True
        except Exception:
            return False


register(FpmConnector())
