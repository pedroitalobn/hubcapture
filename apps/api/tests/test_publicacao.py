"""Publicação — "saiu ou não saiu?" só pode ser respondido pela FONTE.

Regressão do relato do gestor: o Hub anunciava propostas PUBLICADAS que o
TransfereGov mostrava como não publicadas. Os três caminhos do falso positivo
estão cobertos aqui:

1. um VALOR em reais decidindo a resposta (era o mais frequente);
2. o NOME de um arquivo da lista de documentos digitalizados casando "publicado";
3. a chave de topo do jsonb — quem gravasse por último tinha razão, e o pacote
   (~mensal) apagava a consulta ao vivo tanto quanto o contrário.
"""

from __future__ import annotations

from src.connectors import pareceres_siconv
from src.services import publicacao


# ── a régua: só o que a fonte afirma ───────────────────────────────────────
def test_valor_em_reais_nao_publica_nada() -> None:
    """A causa raiz do relato: dinheiro respondendo pergunta de sim/não."""
    assert publicacao.do_execucao({"valor_publicado": "150000"}) == publicacao.SEM_INFORMACAO
    # e com a fonte DIZENDO que não saiu, o valor não pode virar o troco
    ex = {"situacao_publicacao": "Não Publicado", "valor_publicado": "150000"}
    assert publicacao.do_execucao(ex) == publicacao.NAO_PUBLICADO


def test_afirmativa_negativa_e_o_que_nao_e_resposta() -> None:
    assert publicacao.estado("Publicado") == publicacao.PUBLICADO
    assert publicacao.estado("Publicado no D.O.U. de 12/03/2026") == publicacao.PUBLICADO
    assert publicacao.estado("12/03/2026") == publicacao.PUBLICADO
    assert publicacao.estado("Não Publicado") == publicacao.NAO_PUBLICADO
    assert publicacao.estado("Publicação Pendente") == publicacao.NAO_PUBLICADO
    # nada disso é resposta à pergunta — e nenhum vira afirmação
    for ruido in ("sim", "não", "-", "", None, "1234", "Direta"):
        assert publicacao.estado(ruido) == publicacao.SEM_INFORMACAO


def test_frase_solta_nao_e_o_campo() -> None:
    """Nome de arquivo/frase que MENCIONA publicação não é o campo publicação."""
    nome = "Publicacao do extrato publicado no DOU assinado pelo gestor.pdf"
    assert publicacao.estado(nome) == publicacao.SEM_INFORMACAO
    # "republicado" não é "publicado" (casamento por palavra, não substring)
    assert publicacao.estado("republicado") == publicacao.SEM_INFORMACAO


# ── precedência entre as fontes do mesmo jsonb ─────────────────────────────
def test_consulta_ao_vivo_vence_o_pacote_mensal() -> None:
    ex = {
        "situacao_publicacao": "Publicado",  # topo (relatório, o mais antigo)
        "convenio": {"situacao_publicacao": "Publicado"},
        "webapp": {"situacao_publicacao": "Não Publicado"},
    }
    leitura = publicacao.resolver(ex)
    assert leitura.estado == publicacao.NAO_PUBLICADO
    assert leitura.origem and "ao vivo" in leitura.origem


def test_fonte_ilegivel_passa_a_vez_em_vez_de_travar_a_leitura() -> None:
    ex = {
        "valor_empenhado": "390000",  # §56d: publicação precisa de empenho
        "webapp": {"situacao_publicacao": "sim"},
        "convenio": {"situacao_publicacao": "Publicado"},
    }
    leitura = publicacao.resolver(ex)
    assert leitura.estado == publicacao.PUBLICADO
    assert leitura.origem and "pacote" in leitura.origem


def test_data_de_publicacao_so_sai_de_proposta_publicada() -> None:
    """Data residual de outro campo viraria "publicado em …" na tela."""
    assert publicacao.data_publicacao(
        {"situacao_publicacao": "Não publicado", "data_publicacao": "12/03/2026"}
    ) is None
    assert publicacao.data_publicacao(
        {
            "valor_empenhado": "390000",
            "convenio": {"situacao_publicacao": "Publicado", "publicado_em": "12/03/2026"},
        }
    ) is not None


# ── a leitura na PÁGINA: o campo, não o texto ao redor ─────────────────────
_FICHA = """
<table>
  <tr><td>Situação</td><td>Em execução</td><td>Empenhado</td><td>sim</td></tr>
  <tr><td>Publicação</td><td>Não Publicado</td><td>Regime de Execução</td><td>Direta</td></tr>
</table>
<b>Lista de Documentos Digitalizados</b>
<table>
  <tr><td>Publicação do extrato no DOU - publicado.pdf</td><td>12/03/2026</td></tr>
</table>
"""


def test_campo_da_ficha_vence_a_lista_de_documentos() -> None:
    """O documento chamado "…publicado.pdf" não pode publicar a proposta."""
    corpo = "Situação Em execução Empenhado sim Publicação Não Publicado Regime de Execução Direta"
    assert pareceres_siconv._parse_execucao(corpo, _FICHA)["situacao_publicacao"] == (
        "Não Publicado"
    )


def test_campo_ausente_na_ficha_nao_herda_resposta_vizinha() -> None:
    """Sem o campo, o Hub diz "sem informação" — não pega o `sim` do vizinho."""
    html = "<table><tr><td>Empenhado</td><td>sim</td></tr></table>"
    corpo = "Empenhado sim"
    assert "situacao_publicacao" not in pareceres_siconv._parse_execucao(corpo, html)


# ── §56d: publicação sem empenho não existe ────────────────────────────────
def test_publicado_sem_empenho_nao_e_afirmado() -> None:
    """A regra do gestor: proposta publicada SEMPRE tem nota de empenho. Sem
    empenho nenhum, a afirmação da ficha não se sustenta — e é assim que o dado
    ANTIGO, gravado como "Publicado" antes da §56b, para de mentir sem esperar
    re-coleta."""
    leitura = publicacao.resolver({"situacao_publicacao": "Publicado"})
    assert leitura.estado == publicacao.SEM_INFORMACAO
    assert leitura.ressalva == publicacao.RESSALVA_SEM_EMPENHO
    # a declaração da fonte NÃO some: a tela diz o que ela informou e por quê
    assert leitura.situacao == "Publicado" and leitura.origem


def test_rebaixa_para_sem_informacao_e_NUNCA_para_nao_publicado() -> None:
    """Negar por inferência seria o mesmo defeito ao contrário (o falso
    negativo que a §56c evita no DOU)."""
    assert (
        publicacao.resolver({"situacao_publicacao": "Publicado"}).estado
        != publicacao.NAO_PUBLICADO
    )
    # e a NEGATIVA da fonte é consistente com a falta de empenho: fica de pé
    assert (
        publicacao.resolver({"situacao_publicacao": "Não Publicado"}).estado
        == publicacao.NAO_PUBLICADO
    )


def test_as_duas_origens_do_empenho_sustentam_a_publicacao() -> None:
    """O empenho tem duas origens (§56): o agregado da execução e a soma das
    NOTAS. Ignorar a segunda rebaixaria proposta cujo empenho só existe em nota."""
    agregado = {"situacao_publicacao": "Publicado", "valor_empenhado": "390000"}
    assert publicacao.resolver(agregado).estado == publicacao.PUBLICADO

    so_nota = {"situacao_publicacao": "Publicado"}
    assert (
        publicacao.resolver(so_nota, empenho_documentos="390000").estado
        == publicacao.PUBLICADO
    )
    # zero não é empenho
    assert (
        publicacao.resolver(so_nota, empenho_documentos="0").estado
        == publicacao.SEM_INFORMACAO
    )


def test_o_extrato_do_DOU_vence_a_regra_do_empenho() -> None:
    """O DOU é o ATO publicado, com o município e a NE na matéria. Se ele
    confirma e o empenho não está no nosso cache, quem está incompleto somos
    nós — não a publicação."""
    ex = {"dou": {"situacao_publicacao": "Publicado", "url": "https://in.gov.br/x"}}
    leitura = publicacao.resolver(ex)
    assert leitura.estado == publicacao.PUBLICADO
    assert leitura.ressalva is None
