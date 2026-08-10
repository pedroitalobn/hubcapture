"""Connector FNS — Fundo Nacional de Saúde (API do ConsultaFNS + scraping).

O portal de consultas do FNS (consultafns.saude.gov.br) é uma SPA cujo backend
REST responde sob o mesmo host. A API é a fonte PRIMÁRIA; o scraping da página
de consulta segue como 2ª fonte de verdade (coleta combinada, §5/§30): os dois
lados rodam em paralelo e o resultado é fundido — API vence em id/valor/data/
documento, scraping vence nos campos descritivos — com a origem de cada campo
registrada em `proveniencia`.

Autocalibração (§27): a rota exata do backend não é fixa aqui —
  1. rota manual do painel admin (`fns_api_endpoint`), se definida;
  2. candidatos conhecidos, na ordem (o que respondeu fica em cache por base).
Os parâmetros também variam por implantação (código de município em 6 dígitos
vs IBGE de 7) → envia os dois estilos e, quando a resposta ecoa alguma coluna
de IBGE, SEMPRE refiltra no cliente (linha de outro município nunca entra;
resposta sem coluna de IBGE é aceita porque a consulta já foi por município).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Any

from ..core.config import settings
from ..scraping.scraper import get_scraper
from ..services import config as config_service
from ._combinada import coletar
from ._http import ConnectorClientError, get_json
from .base import RawRecord, register

# rotas candidatas do backend do ConsultaFNS — ponto de calibração (§27);
# `fns_api_endpoint` no painel admin vence qualquer candidato
ENDPOINT_CANDIDATES = (
    "repasse/consultar",
    "repasse",
    "pagamento/consultar",
    "pagamento",
    "consulta-detalhada",
)
PAGE_LIMIT = 500
MAX_ANOS = 3  # janela máxima de exercícios consultados por coleta

# chaves onde as respostas costumam embrulhar a lista de linhas
_CHAVES_LISTA = ("items", "content", "registros", "lista", "repasses", "resultado", "dados")

# cache da rota que funcionou, por base_url
_endpoint_cache: dict[str, str] = {}

# schema de extração do scraping (o que o scraper estrutura da página)
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "repasses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "data": {"type": "string"},
                    "acao": {"type": "string"},
                    "categoria": {"type": "string"},
                    "portaria": {"type": "string"},
                    "valor": {"type": "string"},
                    "emenda": {"type": "boolean"},
                },
            },
        }
    },
}


def _digits(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _flag(v: Any) -> bool:
    """Booleano tolerante a texto de fonte ("SIM"/"NÃO"/"S"/"N"/"1"/"0")."""
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("sim", "s", "true", "1", "x")


def _norm_key(k: Any) -> str:
    """camelCase → snake_case minúsculo ("vlRepasse" → "vl_repasse"), para o
    keyword casar igual com JSON camelCase, snake_case e CAIXA ALTA (§35)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(k)).lower()


def _campo(row: dict, *keywords: str) -> Any:
    """Primeiro valor cujo NOME de coluna case com um keyword — na ordem dos
    keywords (prioridade), não na ordem das colunas. "situacao" nunca casa com
    "acao" (senão o status PAGO viraria descrição)."""
    for kw in keywords:
        for k, v in row.items():
            lk = _norm_key(k)
            if kw in lk and not (kw == "acao" and "situacao" in lk):
                return v
    return None


def _tem_coluna_ibge(row: dict) -> bool:
    return any("ibge" in str(k).lower() or "municipio" in str(k).lower() for k in row)


def _linha_do_municipio(row: dict, ibge: str) -> bool:
    """Aceita a linha só se alguma coluna de IBGE/município bater (7 ou 6 dígitos)."""
    for k, v in row.items():
        lk = str(k).lower()
        if "ibge" in lk or "municipio" in lk:
            d = _digits(v)
            if d and (d == ibge or d == ibge[:6]):
                return True
    return False


def _extrair_linhas(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for chave in _CHAVES_LISTA:
            if isinstance(data.get(chave), list):
                return [r for r in data[chave] if isinstance(r, dict)]
        for valor in data.values():  # lista sob chave desconhecida
            if isinstance(valor, list) and valor and isinstance(valor[0], dict):
                return valor
    return []


def _montar_raw(row: dict) -> dict:
    """Mapeia uma linha da API (schema variável, chaves às vezes em CAIXA ALTA)
    para o shape do normalizador de repasse — casamento por palavra-chave."""
    descricao = _campo(row, "descricao", "acao", "item", "objeto") or "Repasse FNS"
    data_repasse = _campo(row, "data", "dt_")
    if not data_repasse:
        ano = _campo(row, "ano", "exercicio")
        mes = _campo(row, "mes")
        if ano and mes and _digits(mes):
            data_repasse = f"{_digits(ano)}-{int(_digits(mes)):02d}-01"
    return {
        "data_repasse": data_repasse,
        "descricao": str(descricao),
        "categoria": _campo(row, "bloco", "componente", "grupo") or "FNS",
        "orgao_superior": "Fundo Nacional de Saúde",
        "natureza": "repasse",
        "valor": row.get("valor") or _campo(row, "valor", "vl_"),
        "competencia": _campo(row, "competencia", "parcela", "referencia"),
        "documento": _campo(row, "portaria", "nu_ob", "numero_ob", "documento", "processo"),
        "emenda": _flag(_campo(row, "emenda")),
        "detalhe": row,
    }


def _raw_do_scrape(item: dict) -> dict:
    return {
        "data_repasse": item.get("data"),
        "descricao": item.get("acao"),
        "categoria": item.get("categoria"),
        "orgao_superior": "Fundo Nacional de Saúde",
        "natureza": "repasse",
        "valor": item.get("valor"),
        "documento": item.get("portaria"),
        "emenda": _flag(item.get("emenda")),
    }


def _id_externo(row: dict, ibge: str) -> str:
    rid = row.get("id") or _campo(row, "id_repasse", "id_pagamento", "nu_ob", "numero_ob")
    if rid:
        return str(rid)
    payload = json.dumps(row, sort_keys=True, default=str, ensure_ascii=False)
    return f"{ibge}:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


# campos em que o scraping tem mais autoridade que a API (§5)
_CAMPOS_SCRAPE_VENCE = ("descricao", "categoria")


def _fundir(api_raw: dict, scrape_raw: dict) -> dict:
    """Funde API + scraping: API é a base; scraping vence nos descritivos."""
    fundido = dict(api_raw)
    prov: dict[str, str] = {}
    for campo in _CAMPOS_SCRAPE_VENCE:
        if scrape_raw.get(campo):
            fundido[campo] = scrape_raw[campo]
            prov[campo] = "scrape"
    if scrape_raw.get("emenda") and not fundido.get("emenda"):
        fundido["emenda"] = True
        prov["emenda"] = "scrape"
    if prov:
        fundido["_proveniencia"] = prov
    return fundido


class FnsConnector:
    source_id = "fns"

    def __init__(self, base_url: str | None = None, api_url: str | None = None) -> None:
        self.base_url = base_url or settings.fns_consulta_url
        self.api_url = api_url or settings.fns_api_url

    async def _rotas_candidatas(self, base: str) -> list[str]:
        override = await config_service.resolver("fns_api_endpoint")
        if override:
            return [override.strip("/")]
        if base in _endpoint_cache:
            return [_endpoint_cache[base]]
        return list(ENDPOINT_CANDIDATES)

    async def _coletar_api(self, municipio_ibge: str, since: date) -> list[dict]:
        base = await config_service.resolver("fns_api_url") or self.api_url
        anos = [str(a) for a in range(since.year, date.today().year + 1)][-MAX_ANOS:]
        ultima_falha: Exception | None = None
        for rota in await self._rotas_candidatas(base):
            linhas: list[dict] = []
            try:
                for ano in anos:
                    # os dois estilos de código de município conhecidos; params
                    # desconhecidos são ignorados e o refiltro local garante
                    data = await get_json(
                        base,
                        rota,
                        {
                            "coMunicipio": municipio_ibge[:6],
                            "coMunicipioIbge": municipio_ibge[:6],
                            "codigoMunicipio": municipio_ibge,
                            "ibge": municipio_ibge,
                            "ano": ano,
                            "pagina": "1",
                            "tamanhoPagina": str(PAGE_LIMIT),
                            "limit": str(PAGE_LIMIT),
                        },
                    )
                    linhas.extend(_extrair_linhas(data))
            except Exception as exc:  # 404/400 → tenta a próxima rota
                ultima_falha = exc
                continue
            if any(_tem_coluna_ibge(r) for r in linhas):
                # a resposta ecoa o município → refiltro estrito (nunca ingere
                # o Brasil inteiro por engano)
                linhas = [r for r in linhas if _linha_do_municipio(r, municipio_ibge)]
            if linhas:
                _endpoint_cache[base] = rota
                return linhas
            ultima_falha = ConnectorClientError(
                f"{rota}: nenhuma linha do município {municipio_ibge}"
            )
        raise ConnectorClientError(
            "nenhuma rota da API do ConsultaFNS respondeu com dados do município — "
            f"defina fns_api_endpoint no painel admin. Última falha: {ultima_falha}"
        )

    async def _coletar_scrape(self, municipio_ibge: str) -> list[dict]:
        scraper = get_scraper()
        base = await config_service.resolver("fns_consulta_url") or self.base_url
        url = f"{base}?ibge={municipio_ibge}"
        dados = await scraper.extract(url, EXTRACT_SCHEMA)  # levanta se não configurado
        itens = dados.get("repasses", []) if isinstance(dados, dict) else []
        return [item for item in itens if isinstance(item, dict)]

    async def collect(self, municipio_ibge: str, since: date) -> list[RawRecord]:
        linhas_api, itens_scrape, erro_api = await coletar(
            lambda: self._coletar_api(municipio_ibge, since),
            lambda: self._coletar_scrape(municipio_ibge),
            fonte=self.source_id,
        )
        if not linhas_api and not itens_scrape and erro_api:
            raise erro_api

        base = await config_service.resolver("fns_api_url") or self.api_url
        rota = _endpoint_cache.get(base, "api")

        # pareamento API ↔ scraping pelo documento (portaria/OB), só por dígitos
        indice_scrape: dict[str, dict] = {}
        for item in itens_scrape:
            chave = _digits(item.get("portaria"))
            if chave:
                indice_scrape[chave] = item

        records: list[RawRecord] = []
        usadas: set[str] = set()
        for row in linhas_api:
            api_raw = _montar_raw(row)
            chave = _digits(api_raw.get("documento"))
            par = indice_scrape.get(chave) if chave else None
            if par is not None:
                usadas.add(chave)
                raw = _fundir(api_raw, _raw_do_scrape(par))
                endpoint = f"{rota}+scrape"
            else:
                raw, endpoint = api_raw, rota
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=_id_externo(row, municipio_ibge),
                    municipio_ibge=municipio_ibge,
                    endpoint=endpoint,
                    raw=raw,
                )
            )

        # linha que só o scraping conhece entra sozinha (a página publica
        # repasse que a API ainda não expõe) — ganho da coleta combinada
        for i, item in enumerate(itens_scrape):
            chave = _digits(item.get("portaria"))
            if chave and chave in usadas:
                continue
            raw = _raw_do_scrape(item)
            raw["_proveniencia"] = {k: "scrape" for k, v in raw.items() if v not in (None, "")}
            records.append(
                RawRecord(
                    source_id=self.source_id,
                    id_externo=str(item.get("portaria") or f"{municipio_ibge}-{i}"),
                    municipio_ibge=municipio_ibge,
                    endpoint="scrape",
                    raw=raw,
                )
            )
        return records

    async def health_check(self) -> bool:
        base = await config_service.resolver("fns_api_url") or self.api_url
        try:
            await get_json(base, "", {})
            return True
        except ConnectorClientError:
            return True  # 4xx na raiz ainda prova que o serviço está de pé
        except Exception:
            return await get_scraper().is_enabled()


register(FnsConnector())
