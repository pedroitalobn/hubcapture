"""Motor de sincronização da agenda ↔ provedores externos.

Regras (as mesmas para Google, Microsoft, Apple/CardDAV — o motor não conhece
provedor):

- **Casamento**: primeiro pelo vínculo (`contato_vinculos`); sem vínculo, pela
  `chave_dedup` (e-mail > telefone > nome+organização). Só então cria.
- **Mudou de que lado?** Compara três hashes: o local, o remoto e o
  `hash_sincronizado` (o que os dois lados tinham na última sync). Um lado
  mudou → aplica. Os dois mudaram → conflito, resolvido por MERGE (une
  e-mails/telefones/tags, preenche vazios) — ninguém perde dado.
- **Remoção**: contato arquivado no Hub → apagado no provedor; item removido no
  provedor → arquivado no Hub. Ausência numa listagem só conta como remoção se
  a leitura foi completa (num delta, ausência não quer dizer nada).
- **Direção**: `importar` só puxa, `exportar` só empurra, `bidirecional` faz os dois.

Falha de provedor não derruba o request: vira `status=erro` na integração +
registro em `sync_runs` (mesma degradação graciosa do sync de obras).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ingestion.normalizer_contato import aplicar_no_modelo, canonizar, do_modelo, mesclar
from ..integrations.contatos import get_provedor
from ..integrations.contatos._http import ProvedorClientError
from ..integrations.contatos.base import Credencial, ProvedorIndisponivel
from ..models.audit_log import AuditLog
from ..models.contato import Contato
from ..models.integracao_contatos import ContatoVinculo, IntegracaoContatos
from ..schemas.contato import SyncResultado
from . import contatos as contatos_service
from . import integracoes_contatos as integracoes_service
from ._sync import registrar_sync

MAX_ERRO = 2000


async def sincronizar(
    session: AsyncSession,
    *,
    usuario_id: uuid.UUID,
    integracao: IntegracaoContatos,
    tipo: str = "avulso",
) -> SyncResultado:
    resultado = SyncResultado(
        integracao_id=integracao.id,
        provedor=integracao.provedor,
        conta=integracao.conta,
        status="ok",
    )
    if not integracao.ativo:
        resultado.status = "desabilitada"
        return resultado

    iniciado = datetime.now(UTC)
    cred = integracoes_service.credencial(integracao)
    try:
        provedor = get_provedor(integracao.provedor)
        if not cred.dados:
            raise ProvedorIndisponivel("credenciais ausentes — reconecte a conta")

        if integracao.direcao in ("bidirecional", "importar"):
            await _importar(session, usuario_id, integracao, provedor, cred, resultado)
        if integracao.direcao in ("bidirecional", "exportar"):
            await _exportar(session, integracao, provedor, cred, resultado)

        integracao.status = "conectada"
        integracao.ultimo_erro = None
    except Exception as exc:  # noqa: BLE001 — o incidente vira status + sync_run
        resultado.status = "erro"
        resultado.erro = f"{type(exc).__name__}: {exc}"[:MAX_ERRO]
        integracao.status = (
            "expirada"
            if isinstance(exc, ProvedorClientError) and exc.auth_expirada
            else "erro"
        )
        integracao.ultimo_erro = resultado.erro
    finally:
        # o provedor pode ter renovado o access token mesmo numa sync que falhou
        integracoes_service.salvar_credencial(integracao, cred)
        integracao.ultima_sync_em = datetime.now(UTC)
        integracao.total_contatos = await _total_vinculos(session, integracao.id)
        await session.flush()
        await registrar_sync(
            usuario_id=usuario_id,
            fonte=f"contatos_{integracao.provedor}"[:32],
            tipo=tipo,
            status="ok" if resultado.status == "ok" else "erro",
            registros=resultado.importados
            + resultado.atualizados_local
            + resultado.exportados
            + resultado.atualizados_remoto,
            iniciado_em=iniciado,
            finalizado_em=datetime.now(UTC),
            erro=resultado.erro,
        )
    return resultado


async def sincronizar_todas(
    session: AsyncSession, *, usuario_id: uuid.UUID, tipo: str = "avulso"
) -> list[SyncResultado]:
    """Best-effort: uma integração que falha não impede as outras."""
    saida: list[SyncResultado] = []
    for integracao in await integracoes_service.listar(session):
        if not integracao.ativo:
            continue
        saida.append(
            await sincronizar(
                session, usuario_id=usuario_id, integracao=integracao, tipo=tipo
            )
        )
    session.add(
        AuditLog(usuario_id=usuario_id, acao="sync_contatos", entidade=str(len(saida)))
    )
    return saida


# ── importação (provedor → Hub) ──────────────────────────────────────────────


async def _importar(
    session: AsyncSession,
    usuario_id: uuid.UUID,
    integracao: IntegracaoContatos,
    provedor,
    cred: Credencial,
    resultado: SyncResultado,
) -> None:
    pagina = await provedor.listar(cred, integracao.sync_token)
    vinculos = await _vinculos_por_externo(session, integracao.id)
    # dois contatos remotos podem casar no MESMO contato local (mesmo e-mail de
    # gabinete, por exemplo). O vínculo é 1-1 por (integração, contato): o
    # primeiro fica; o segundo só atualiza a agenda, sem criar vínculo duplicado.
    ja_vinculados: set[uuid.UUID] = {v.contato_id for v in vinculos.values()}
    vistos: set[str] = set()

    for item in pagina.itens:
        if not item.id_externo:
            continue
        vistos.add(item.id_externo)
        vinculo = vinculos.get(item.id_externo)

        if item.removido:
            if vinculo is not None:
                await _arquivar_por_vinculo(session, vinculo, resultado)
            continue
        if item.canonico is None:
            continue

        canonico = canonizar(item.canonico)
        if vinculo is None:
            contato, criado = await contatos_service.upsert_canonico(
                session,
                usuario_id=usuario_id,
                canonico=canonico,
                origem=integracao.provedor,
            )
            if criado:
                resultado.importados += 1
            else:
                # casou com um contato que já existia na agenda: os dois lados
                # somam. `hash_sincronizado` fica no hash REMOTO, então o passo
                # de exportação leva o resultado mesclado de volta ao provedor.
                resultado.atualizados_local += 1
            if contato.id not in ja_vinculados:
                ja_vinculados.add(contato.id)
                session.add(
                    ContatoVinculo(
                        integracao_id=integracao.id,
                        contato_id=contato.id,
                        id_externo=item.id_externo,
                        etag=item.etag,
                        hash_sincronizado=canonico.hash_conteudo,
                    )
                )
            continue

        contato = await session.get(Contato, vinculo.contato_id)
        if contato is None:
            await session.delete(vinculo)
            continue

        base = vinculo.hash_sincronizado
        if canonico.hash_conteudo != base:  # o remoto mudou desde a última sync
            if contato.hash_conteudo in (base, canonico.hash_conteudo):
                aplicar_no_modelo(contato, canonico)  # local intacto → remoto manda
                resultado.atualizados_local += 1
            else:
                aplicar_no_modelo(contato, mesclar(do_modelo(contato), canonico))
                resultado.conflitos += 1
            contato.updated_at = datetime.now(UTC)
        vinculo.etag = item.etag
        vinculo.hash_sincronizado = canonico.hash_conteudo

    if pagina.completa:
        # leitura completa: o que sumiu do provedor foi removido de lá
        for id_externo, vinculo in vinculos.items():
            if id_externo not in vistos:
                await _arquivar_por_vinculo(session, vinculo, resultado)

    integracao.sync_token = pagina.sync_token
    await session.flush()


async def _arquivar_por_vinculo(
    session: AsyncSession, vinculo: ContatoVinculo, resultado: SyncResultado
) -> None:
    contato = await session.get(Contato, vinculo.contato_id)
    if contato is not None and not contato.arquivado:
        contato.arquivado = True
        contato.updated_at = datetime.now(UTC)
        resultado.removidos_local += 1
    await session.delete(vinculo)


# ── exportação (Hub → provedor) ──────────────────────────────────────────────


async def _exportar(
    session: AsyncSession,
    integracao: IntegracaoContatos,
    provedor,
    cred: Credencial,
    resultado: SyncResultado,
) -> None:
    vinculos = await _vinculos_por_contato(session, integracao.id)
    contatos = list(
        (await session.execute(select(Contato).order_by(Contato.created_at)))
        .scalars()
        .all()
    )

    for contato in contatos:
        vinculo = vinculos.get(contato.id)

        if contato.arquivado:
            if vinculo is not None:
                await provedor.remover(cred, vinculo.id_externo, vinculo.etag)
                await session.delete(vinculo)
                resultado.removidos_remoto += 1
            continue

        canonico = do_modelo(contato)
        if vinculo is None:
            externo = await provedor.criar(cred, canonico)
            session.add(
                ContatoVinculo(
                    integracao_id=integracao.id,
                    contato_id=contato.id,
                    id_externo=externo.id_externo,
                    etag=externo.etag,
                    hash_sincronizado=canonico.hash_conteudo,
                )
            )
            resultado.exportados += 1
        elif contato.hash_conteudo != vinculo.hash_sincronizado:
            externo = await provedor.atualizar(
                cred, vinculo.id_externo, vinculo.etag, canonico
            )
            if externo.id_externo:
                vinculo.id_externo = externo.id_externo
            vinculo.etag = externo.etag or vinculo.etag
            vinculo.hash_sincronizado = canonico.hash_conteudo
            resultado.atualizados_remoto += 1

    await session.flush()


# ── consultas auxiliares ─────────────────────────────────────────────────────


async def _vinculos(
    session: AsyncSession, integracao_id: uuid.UUID
) -> list[ContatoVinculo]:
    stmt = select(ContatoVinculo).where(ContatoVinculo.integracao_id == integracao_id)
    return list((await session.execute(stmt)).scalars().all())


async def _vinculos_por_externo(
    session: AsyncSession, integracao_id: uuid.UUID
) -> dict[str, ContatoVinculo]:
    return {v.id_externo: v for v in await _vinculos(session, integracao_id)}


async def _vinculos_por_contato(
    session: AsyncSession, integracao_id: uuid.UUID
) -> dict[uuid.UUID, ContatoVinculo]:
    return {v.contato_id: v for v in await _vinculos(session, integracao_id)}


async def _total_vinculos(session: AsyncSession, integracao_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(ContatoVinculo)
        .where(ContatoVinculo.integracao_id == integracao_id)
    )
    return int((await session.execute(stmt)).scalar_one())


async def limpar_arquivados(session: AsyncSession) -> int:
    """Apaga de vez os contatos arquivados que já não têm vínculo pendente.

    Chamado depois do sync: o tombstone só existe para propagar a remoção; sem
    vínculo, não há mais provedor para avisar.
    """
    pendentes = select(ContatoVinculo.contato_id)
    stmt = (
        delete(Contato)
        .where(Contato.arquivado.is_(True), Contato.id.not_in(pendentes))
        .returning(Contato.id)
    )
    return len(list((await session.execute(stmt)).scalars().all()))
