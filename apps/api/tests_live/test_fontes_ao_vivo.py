"""Smoke test AO VIVO das fontes — responde "a API está funcional?" com asserção.

Fica FORA de `tests/` de propósito: o conftest de lá tem fixture autouse que
exige Postgres, e verificar fonte viva não deve depender de banco (mesma
filosofia do probe, §30). Também não roda por padrão — sandboxes de CI/agente
costumam bloquear *.gov.br, e teste que depende de serviço de terceiro não
pode derrubar a suíte. Ligue explicitamente, de uma máquina com saída:

    cd apps/api
    LIVE_FONTES=fns uv run pytest tests_live/ -q -s
    LIVE_FONTES=all LIVE_IBGE=2611606 uv run pytest tests_live/ -q -s

`LIVE_FONTES` aceita connector ids separados por vírgula, ou `all` para todas
as HABILITADAS. Aprovação exige, por fonte: `health_check` True E `collect`
com >=1 registro para o município (São Paulo por padrão — município grande
recebe repasse todo mês; vazio ali é sintoma, não normalidade). O relatório
com os CAMPOS reais sai no stdout (`-s`) — é o que se calibra (§27/§30b).
Reusa o `_probe` de `tools/probe_fontes` para haver UMA definição do que é
"fonte respondendo".
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest

from src.services import fontes as fontes_service
from src.tools.probe_fontes import _probe  # importa e registra os connectors

_LIVE = os.getenv("LIVE_FONTES", "").strip()
IBGE = os.getenv("LIVE_IBGE", "3550308").strip()
DIAS = int(os.getenv("LIVE_DIAS", "365"))
TIMEOUT = float(os.getenv("LIVE_TIMEOUT", "180"))

pytestmark = pytest.mark.skipif(
    not _LIVE,
    reason="teste ao vivo: defina LIVE_FONTES=fns (ou 'all') numa máquina com saída p/ gov.br",
)


def _fontes_alvo() -> list[str]:
    if _LIVE.lower() in ("1", "all", "todas"):
        return list(fontes_service.HABILITADAS)
    return [f.strip() for f in _LIVE.split(",") if f.strip()]


@pytest.mark.parametrize("fonte", _fontes_alvo() or ["fns"])
async def test_fonte_ao_vivo_responde_com_dados(fonte: str) -> None:
    since = date.today() - timedelta(days=DIAS)
    linha = await _probe(fonte, IBGE, since, TIMEOUT)

    # o relatório completo é parte do valor do teste: campos reais = calibração
    print(f"\n[{fonte}] {json.dumps(linha, ensure_ascii=False, indent=2, default=str)}")

    assert linha.get("health_check") is True, f"{fonte}: health_check falhou — {linha}"
    assert linha["status"] == "ok", (
        f"{fonte}: sem dados ao vivo (status={linha['status']}) — "
        f"{linha.get('erro', 'município sem registros no período?')}"
    )
    assert linha["registros"] >= 1
