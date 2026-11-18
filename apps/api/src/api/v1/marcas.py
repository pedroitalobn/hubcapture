"""White label (§69) — rotas públicas do site, do dono da marca e do admin.

- `/branding*` é PÚBLICO: a tela de login sai vestida antes de existir sessão.
- `/brands/*` é de quem EDITA a marca: o dono ou um superuser. Campos de
  operação (slug, ativação, dono, plano) só o admin muda.
- `/admin/brands*` cria/exclui marcas e força ativação de domínio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.users import current_active_user, current_superuser
from ...models.convite import Convite
from ...models.marca import TIPOS_ASSET, Marca
from ...models.usuario import Usuario
from ...schemas.marcas import (
    AssetInfo,
    BrandingRead,
    ConviteMarcaCreate,
    DominioUpdate,
    MarcaCreate,
    MarcaRead,
    MarcaUpdate,
    MembroMarca,
    OpcaoCatalogo,
    OpcoesMarca,
    PreviewRead,
    PreviewRequest,
)
from ...schemas.planos import ConviteCreate, ConviteRead
from ...services import dominios, gestao_usuarios
from ...services import marcas as service
from ..deps import get_platform_db

router = APIRouter(tags=["white label"])


# ── Público ─────────────────────────────────────────────────────────────────


@router.get("/branding", response_model=BrandingRead)
async def branding(
    request: Request,
    response: Response,
    host: str | None = Query(default=None, description="Host a resolver (padrão: o da requisição)"),
    session: AsyncSession = Depends(get_platform_db),
) -> BrandingRead:
    """Identidade visual do host. Sem marca (ou host da plataforma) = Hub Capture."""
    alvo = host or service.host_da_requisicao(request.headers)
    marca = await service.por_host(session, alvo)
    # cache curto: a troca de cor no editor aparece em até um minuto
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["Vary"] = "Host, X-Forwarded-Host"
    return await service.branding(session, marca)


@router.get("/branding/assets/{marca_id}/{tipo}")
async def branding_asset(
    marca_id: uuid.UUID,
    tipo: str,
    v: str | None = None,
    session: AsyncSession = Depends(get_platform_db),
) -> Response:
    if tipo not in TIPOS_ASSET:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    asset = await service.ler_asset(session, marca_id, tipo)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    headers = {
        # com ?v=<hash> a URL muda a cada upload — pode ficar no cache para sempre
        "Cache-Control": "public, max-age=31536000, immutable" if v else "public, max-age=300",
        "X-Content-Type-Options": "nosniff",
        # SVG aberto direto na aba não executa nada (o arquivo já é sanitizado)
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "Access-Control-Allow-Origin": "*",  # fontes servidas a outro host da marca
    }
    return Response(content=asset.conteudo, media_type=asset.content_type, headers=headers)


@router.post("/branding/preview", response_model=PreviewRead)
async def branding_preview(
    body: PreviewRequest,
    _user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> PreviewRead:
    """CSS do tema em edição, escopado em `.marca-preview` (o editor pinta só a
    pré-visualização, não o próprio painel)."""
    enviadas: dict[str, str] = {}
    if body.marca_id:
        marca = await session.get(Marca, body.marca_id)
        if marca is not None:
            for a in (await service.ler(session, marca)).assets:
                if a.tipo.startswith("fonte_"):
                    enviadas[a.tipo.removeprefix("fonte_")] = a.url
    return PreviewRead(
        css=service.montar_css(body.tema, seletor=".marca-preview", fontes_enviadas=enviadas),
        fontes_urls=service.fontes_google(body.tema),
        avisos=service.avisos_de_contraste(body.tema),
    )


# ── Dono da marca (ou admin) ────────────────────────────────────────────────


@router.get("/brands/options", response_model=OpcoesMarca)
async def opcoes(_user: Usuario = Depends(current_active_user)) -> OpcoesMarca:
    return OpcoesMarca(
        fontes=[OpcaoCatalogo(chave=k, rotulo=v["rotulo"]) for k, v in service.FONTES.items()],
        formas=[OpcaoCatalogo(chave=k, rotulo=v["rotulo"]) for k, v in service.FORMAS.items()],
        icones=[OpcaoCatalogo(chave=k, rotulo=v[0]) for k, v in service.TRACOS.items()],
        tipos_asset=[OpcaoCatalogo(chave=k, rotulo=v) for k, v in service.ROTULO_ASSET.items()],
        dominio_base=await service.dominio_base(),
        provisionador=await dominios.modo(),
    )


@router.get("/brands/mine", response_model=list[MarcaRead])
async def minhas(
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[MarcaRead]:
    rows = await session.execute(select(Marca).where(Marca.dono_id == user.id).order_by(Marca.nome))
    return [await service.ler(session, m) for m in rows.scalars().all()]


@router.get("/brands/{marca_id}", response_model=MarcaRead)
async def obter(
    marca_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> MarcaRead:
    return await service.ler(session, await service.obter_editavel(session, marca_id, user))


@router.patch("/brands/{marca_id}", response_model=MarcaRead)
async def editar(
    marca_id: uuid.UUID,
    body: MarcaUpdate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> MarcaRead:
    marca = await service.obter_editavel(session, marca_id, user)
    slug_antigo = marca.slug
    await service.atualizar(session, marca, body, admin=user.is_superuser)
    if marca.slug != slug_antigo:
        base = await service.dominio_base()
        await _provisionar_subdominio(marca, base, antigo=f"{slug_antigo}.{base}")
    return await service.ler(session, marca)


@router.put("/brands/{marca_id}/assets/{tipo}", response_model=AssetInfo)
async def enviar_asset(
    marca_id: uuid.UUID,
    tipo: str,
    arquivo: UploadFile = File(...),
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> AssetInfo:
    marca = await service.obter_editavel(session, marca_id, user)
    # lê com teto: um upload gigante não pode ocupar a memória inteira antes
    # da validação recusar
    conteudo = await arquivo.read(4 * 1024 * 1024 + 1)
    return await service.salvar_asset(
        session, marca, tipo, conteudo, arquivo.filename, arquivo.content_type
    )


@router.delete("/brands/{marca_id}/assets/{tipo}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_asset(
    marca_id: uuid.UUID,
    tipo: str,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    marca = await service.obter_editavel(session, marca_id, user)
    await service.remover_asset(session, marca, tipo)


@router.put("/brands/{marca_id}/domain", response_model=MarcaRead)
async def definir_dominio(
    marca_id: uuid.UUID,
    body: DominioUpdate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> MarcaRead:
    """Grava (ou remove, com `null`) o domínio próprio. Fica `pendente` até a
    verificação do DNS; o host antigo perde a rota."""
    marca = await service.obter_editavel(session, marca_id, user)
    antigo = await service.definir_dominio(session, marca, body.dominio)
    if antigo:
        r = await dominios.desprovisionar(antigo)
        service.registrar_provisionamento(marca, antigo, "removido", r.detalhe)
        await session.flush()
    return await service.ler(session, marca)


@router.post("/brands/{marca_id}/domain/verify", response_model=MarcaRead)
async def verificar_dominio(
    marca_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> MarcaRead:
    """Confere o DNS e, apontando para nós, provisiona rota + HTTPS."""
    marca = await service.obter_editavel(session, marca_id, user)
    if not marca.dominio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "SEM_DOMINIO")
    alvo = await service.cname_alvo(marca)
    ok, detalhe = service.comparar_dns(
        await service.resolver_ips(marca.dominio), await service.resolver_ips(alvo)
    )
    if not ok:
        # domínio que JÁ estava ativo não volta a "erro" por uma consulta de
        # DNS que falhou agora (propagação, resolvedor instável)
        if marca.dominio_status != "ativo":
            marca.dominio_status = "erro"
        marca.dominio_detalhe = detalhe
    else:
        marca.dominio_verificado_em = datetime.now(UTC)
        r = await dominios.provisionar(marca.dominio)
        service.registrar_provisionamento(marca, marca.dominio, r.status, r.detalhe)
        marca.dominio_status = (
            "ativo" if r.status == "ok" else ("erro" if r.status == "erro" else "verificado")
        )
        marca.dominio_detalhe = f"{detalhe} {r.detalhe}"
    await session.flush()
    service.limpar_cache()
    return await service.ler(session, marca)


@router.get("/brands/{marca_id}/members", response_model=list[MembroMarca])
async def membros(
    marca_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[MembroMarca]:
    marca = await service.obter_editavel(session, marca_id, user)
    return [
        MembroMarca(
            id=u.id,
            email=u.email,
            nome=u.nome,
            papel=u.papel,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in await service.membros(session, marca)
    ]


@router.delete("/brands/{marca_id}/members/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def desvincular_membro(
    marca_id: uuid.UUID,
    usuario_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    """Tira a conta da marca (ela volta a assinar como Hub Capture). Não exclui
    a conta nem toca nos dados dela."""
    marca = await service.obter_editavel(session, marca_id, user)
    if usuario_id == marca.dono_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "DONO_NAO_SAI: troque o dono antes")
    await session.execute(
        update(Usuario)
        .where(Usuario.id == usuario_id, Usuario.marca_id == marca.id)
        .values(marca_id=None)
    )
    service.limpar_cache()


@router.get("/brands/{marca_id}/invites", response_model=list[ConviteRead])
async def convites(
    marca_id: uuid.UUID,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> list[ConviteRead]:
    marca = await service.obter_editavel(session, marca_id, user)
    rows = await session.execute(
        select(Convite).where(Convite.marca_id == marca.id).order_by(Convite.created_at.desc())
    )
    return [ConviteRead.model_validate(c) for c in rows.scalars().all()]


@router.post("/brands/{marca_id}/invites", response_model=ConviteRead, status_code=201)
async def convidar(
    marca_id: uuid.UUID,
    body: ConviteMarcaCreate,
    user: Usuario = Depends(current_active_user),
    session: AsyncSession = Depends(get_platform_db),
) -> ConviteRead:
    """Convida alguém para a marca: quem aceita entra vinculado a ela, com o
    plano da marca, e o e-mail do convite já sai com a identidade dela."""
    marca = await service.obter_editavel(session, marca_id, user)
    convite = await gestao_usuarios.criar_convite(
        session,
        ConviteCreate(
            email=body.email,
            papel=body.papel or "equipe",
            plano_id=marca.plano_id,
            expires_em_dias=body.expires_em_dias or 7,
        ),
        convidado_por=user.id,
        marca_id=marca.id,
    )
    return ConviteRead.model_validate(convite)


# ── Admin ───────────────────────────────────────────────────────────────────


async def _provisionar_subdominio(marca: Marca, base: str, antigo: str | None = None) -> None:
    if antigo:
        r = await dominios.desprovisionar(antigo)
        service.registrar_provisionamento(marca, antigo, "removido", r.detalhe)
    host = service.host_padrao(marca, base)
    if await dominios.subdominio_coberto():
        service.registrar_provisionamento(marca, host, "ok", "Coberto pelo wildcard do proxy.")
        return
    r = await dominios.provisionar(host)
    service.registrar_provisionamento(marca, host, r.status, r.detalhe)


@router.get("/admin/brands", response_model=list[MarcaRead])
async def admin_listar(
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> list[MarcaRead]:
    rows = await session.execute(select(Marca).order_by(Marca.nome))
    return [await service.ler(session, m) for m in rows.scalars().all()]


@router.post("/admin/brands", response_model=MarcaRead, status_code=201)
async def admin_criar(
    body: MarcaCreate,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> MarcaRead:
    marca = await service.criar(
        session,
        slug=body.slug,
        nome=body.nome,
        dono_email=str(body.dono_email) if body.dono_email else None,
        plano_id=body.plano_id,
        tema=body.tema,
    )
    await _provisionar_subdominio(marca, await service.dominio_base())
    await session.flush()
    return await service.ler(session, marca)


@router.post("/admin/brands/{marca_id}/provision", response_model=MarcaRead)
async def admin_reprovisionar(
    marca_id: uuid.UUID,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> MarcaRead:
    """Refaz o provisionamento do subdomínio (e do domínio, se verificado)."""
    marca = await session.get(Marca, marca_id)
    if marca is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MARCA_NAO_ENCONTRADA")
    await _provisionar_subdominio(marca, await service.dominio_base())
    if marca.dominio and marca.dominio_status in ("verificado", "ativo", "erro"):
        r = await dominios.provisionar(marca.dominio)
        service.registrar_provisionamento(marca, marca.dominio, r.status, r.detalhe)
        if r.status == "ok":
            marca.dominio_status = "ativo"
    await session.flush()
    service.limpar_cache()
    return await service.ler(session, marca)


@router.post("/admin/brands/{marca_id}/domain/activate", response_model=MarcaRead)
async def admin_ativar_dominio(
    marca_id: uuid.UUID,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> MarcaRead:
    """Ativação MANUAL: a equipe confirmou rota + HTTPS no proxy."""
    marca = await session.get(Marca, marca_id)
    if marca is None or not marca.dominio:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SEM_DOMINIO")
    marca.dominio_status = "ativo"
    marca.dominio_detalhe = "Ativado manualmente pela administração."
    service.registrar_provisionamento(marca, marca.dominio, "ok", marca.dominio_detalhe)
    await session.flush()
    service.limpar_cache()
    return await service.ler(session, marca)


@router.delete("/admin/brands/{marca_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_excluir(
    marca_id: uuid.UUID,
    _admin: Usuario = Depends(current_superuser),
    session: AsyncSession = Depends(get_platform_db),
) -> None:
    """Exclui a marca. As contas vinculadas NÃO são excluídas: voltam a ser
    Hub Capture (FK SET NULL); as rotas dos hosts dela são removidas."""
    marca = await session.get(Marca, marca_id)
    if marca is None:
        return
    base = await service.dominio_base()
    for host in (service.host_padrao(marca, base), marca.dominio):
        if host and not (host.endswith("." + base) and await dominios.subdominio_coberto()):
            await dominios.desprovisionar(host)
    await session.delete(marca)
    await session.flush()
    service.limpar_cache()
