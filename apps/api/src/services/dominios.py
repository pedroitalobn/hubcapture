"""Provisionamento de rota + HTTPS dos hosts das marcas (white label, §69).

Um host novo (o subdomínio da marca ou o domínio próprio, depois de o DNS
apontar para nós) só funciona quando o proxy de borda tem uma ROTA para ele e
um CERTIFICADO. Quem cria isso depende da operação — `whitelabel_provisionador`:

- `manual` (padrão): nada é feito; o painel mostra "aguardando ativação" e a
  equipe cadastra o domínio no Dokploy. O admin marca como ativo depois.
- `traefik_arquivo`: escreve um YAML por host na pasta do provider de arquivos
  do Traefik (no Dokploy, `/etc/dokploy/traefik/dynamic`, montada na API). O
  Traefik observa a pasta: rota e certificado Let's Encrypt saem em segundos,
  SEM redeploy. É o caminho recomendado.
- `dokploy`: cria o domínio pela API do Dokploy (`domain.create`). ATENÇÃO:
  domínio de serviço de COMPOSE vira label Docker e só vale no PRÓXIMO deploy
  do compose — com `dokploy_redeploy=on` o provisionamento dispara o deploy
  (rebuild do stack); sem ele, o domínio fica "criado, ativa no próximo deploy".

Nenhum caminho levanta exceção para o chamador: o resultado diz o que houve,
e a marca guarda o estado por host (`marcas.provisionamento`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..core.config import settings
from . import config as config_service

log = logging.getLogger("hubcapture.dominios")

MODOS = ("manual", "traefik_arquivo", "dokploy")

_HOST = re.compile(r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")


@dataclass(frozen=True)
class Resultado:
    status: str  # ok | manual | erro
    detalhe: str


async def _cfg(chave: str, padrao: str = "") -> str:
    return ((await config_service.resolver(chave)) or padrao).strip()


async def modo() -> str:
    m = (await _cfg("whitelabel_provisionador", settings.whitelabel_provisionador)).lower()
    return m if m in MODOS else "manual"


def _nome_arquivo(host: str) -> str:
    return "hubcapture-wl-" + host.replace(".", "-") + ".yml"


def yaml_traefik(
    host: str, servico: str, certresolver: str, entrada_http: str, entrada_https: str
) -> str:
    """Config dinâmica do Traefik para UM host (puro, sem PyYAML).

    `host` chega validado pelo regex de hostname — nada de crase ou aspas que
    escapem da regra `Host(...)`. Router HTTPS com certResolver + router HTTP
    que só redireciona (o desafio HTTP-01 do Let's Encrypt é atendido pelo
    próprio Traefik antes do redirecionamento).
    """
    if not _HOST.match(host):
        raise ValueError(f"host inválido: {host!r}")
    nome = "hcwl-" + host.replace(".", "-")
    return (
        "# gerado pelo Hub Capture (white label) — não editar à mão\n"
        "http:\n"
        "  routers:\n"
        f"    {nome}:\n"
        f'      rule: "Host(`{host}`)"\n'
        f"      entryPoints: [{entrada_https}]\n"
        f"      service: {nome}\n"
        "      tls:\n"
        f"        certResolver: {certresolver}\n"
        f"    {nome}-http:\n"
        f'      rule: "Host(`{host}`)"\n'
        f"      entryPoints: [{entrada_http}]\n"
        f"      middlewares: [{nome}-https]\n"
        f"      service: {nome}\n"
        "  middlewares:\n"
        f"    {nome}-https:\n"
        "      redirectScheme:\n"
        "        scheme: https\n"
        "        permanent: true\n"
        "  services:\n"
        f"    {nome}:\n"
        "      loadBalancer:\n"
        "        servers:\n"
        f'          - url: "{servico}"\n'
    )


async def _traefik(host: str, remover: bool) -> Resultado:
    pasta = await _cfg("whitelabel_traefik_dir", settings.whitelabel_traefik_dir)
    if not pasta:
        return Resultado("erro", "whitelabel_traefik_dir não configurado no painel admin.")
    caminho = Path(pasta) / _nome_arquivo(host)
    try:
        if remover:
            caminho.unlink(missing_ok=True)
            return Resultado("ok", "Rota removida do Traefik.")
        entradas = (await _cfg("whitelabel_traefik_entrypoints", "web,websecure")).split(",")
        http_, https_ = (e.strip() for e in (entradas + ["websecure"])[:2])
        conteudo = yaml_traefik(
            host,
            await _cfg("whitelabel_traefik_servico", settings.whitelabel_traefik_servico),
            await _cfg("whitelabel_traefik_certresolver", "letsencrypt"),
            http_ or "web",
            https_ or "websecure",
        )
        temporario = caminho.with_suffix(".tmp")
        temporario.write_text(conteudo, encoding="utf-8")
        temporario.replace(caminho)  # atômico: o Traefik nunca lê arquivo pela metade
    except (OSError, ValueError) as exc:
        log.warning("traefik: falha ao escrever %s", caminho, exc_info=True)
        return Resultado("erro", f"Não foi possível escrever a rota do Traefik: {exc}")
    return Resultado(
        "ok", "Rota criada no Traefik — o certificado HTTPS sai em instantes (Let's Encrypt)."
    )


async def _dokploy(host: str, remover: bool) -> Resultado:
    url = (await _cfg("dokploy_url", settings.dokploy_url)).rstrip("/")
    chave = await _cfg("dokploy_api_key")
    compose = await _cfg("dokploy_compose_id", settings.dokploy_compose_id)
    if not (url and chave and compose):
        return Resultado("erro", "Dokploy sem URL, API key ou composeId no painel admin.")
    cab = {"x-api-key": chave, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(base_url=f"{url}/api", headers=cab, timeout=20) as cli:
            if remover:
                r = await cli.get("/domain.byComposeId", params={"composeId": compose})
                r.raise_for_status()
                for d in r.json() or []:
                    if isinstance(d, dict) and d.get("host") == host and d.get("domainId"):
                        (
                            await cli.post("/domain.delete", json={"domainId": d["domainId"]})
                        ).raise_for_status()
                return Resultado("ok", "Domínio removido do Dokploy (vale no próximo deploy).")
            corpo = {
                "composeId": compose,
                "serviceName": await _cfg("dokploy_servico", "web"),
                "domainType": "compose",
                "host": host,
                "path": "/",
                "port": 3000,
                "https": True,
                "certificateType": "letsencrypt",
            }
            (await cli.post("/domain.create", json=corpo)).raise_for_status()
            if (await _cfg("dokploy_redeploy", "off")).lower() == "on":
                (await cli.post("/compose.deploy", json={"composeId": compose})).raise_for_status()
                return Resultado("ok", "Domínio criado no Dokploy e deploy disparado.")
            return Resultado(
                "manual",
                "Domínio criado no Dokploy. Em serviço de compose ele só vale no PRÓXIMO "
                "deploy — faça o deploy pelo painel do Dokploy para ativar.",
            )
    except httpx.HTTPError as exc:
        log.warning("dokploy: falha para %s", host, exc_info=True)
        return Resultado("erro", f"A API do Dokploy recusou o pedido: {exc}")


async def provisionar(host: str) -> Resultado:
    if settings.sandbox:
        return Resultado("manual", "Sandbox: domínios não são provisionados neste ambiente.")
    m = await modo()
    if m == "traefik_arquivo":
        return await _traefik(host, remover=False)
    if m == "dokploy":
        return await _dokploy(host, remover=False)
    return Resultado(
        "manual",
        "Aguardando ativação: a equipe da plataforma cadastra o domínio no proxy e emite o HTTPS.",
    )


async def desprovisionar(host: str) -> Resultado:
    if settings.sandbox:
        return Resultado("manual", "Sandbox.")
    m = await modo()
    if m == "traefik_arquivo":
        return await _traefik(host, remover=True)
    if m == "dokploy":
        return await _dokploy(host, remover=True)
    return Resultado("manual", "Remova o domínio do proxy manualmente.")


async def subdominio_coberto() -> bool:
    """Subdomínios já atendidos por um wildcard no proxy (*.base) — nada a criar."""
    return (await _cfg("whitelabel_subdominio_wildcard", "off")).lower() == "on"
