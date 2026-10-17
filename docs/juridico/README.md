# Documentos jurídicos — Hub Capture

## `Averbacao_Hub_Capture.docx`

Declaração de autoria e titularidade + memorial descritivo do programa de
computador **Hub Capture**, para instruir:

- pedido de **registro de programa de computador** no INPI (Lei nº 9.609/1998); e/ou
- **averbação/registro** em Cartório de Registro de Títulos e Documentos.

Autoria considerada **pessoa física** (criação independente, sem vínculo
empregatício — afasta o art. 4º da Lei nº 9.609/1998).

### Antes de assinar / protocolar

1. Preencher os campos entre colchetes em **negrito** (item I — qualificação, e o
   fecho: cidade, UF, data, assinaturas e testemunhas).
2. Regerar o hash SHA-512 sobre o arquivo de código-fonte que será efetivamente
   depositado e atualizar o item III:

   ```bash
   git archive --format=tar HEAD | sha512sum
   ```

3. Conferir a volumetria (item IX) e a estrutura de módulos (Anexo I) se o código
   tiver evoluído desde a revisão declarada.

O Anexo II lista o checklist completo do depósito.

### Regenerar o documento

```bash
npm i docx
node docs/juridico/gerar_averbacao.js docs/juridico/Averbacao_Hub_Capture.docx
```

Os dados técnicos (datas, revisão, volumetria, hash) estão no topo do script e nas
tabelas — atualize-os antes de regerar para uma nova versão do software.
