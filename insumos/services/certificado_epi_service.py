from django.core.exceptions import ValidationError
from django.db import transaction

from insumos.models import CertificadoEpi, Insumo, ProdutoEpi


class CertificadoEpiService:
    """Mantém um CA canônico no produto, compartilhado por suas variantes."""

    @staticmethod
    def normalizar_numero(numero_ca):
        return (numero_ca or '').strip().upper()

    @classmethod
    @transaction.atomic
    def registrar(
        cls,
        *,
        produto_epi,
        numero_ca,
        validade_ca=None,
        observacao='',
        ativo=True,
        situacao_oficial='',
        snapshot_oficial=None,
        consultado_em=None,
        importacao_caepi=None,
    ):
        if not isinstance(produto_epi, ProdutoEpi):
            raise ValidationError({'produto_epi': 'Informe um produto EPI válido.'})
        if produto_epi.insumo.natureza != Insumo.Natureza.EPI:
            raise ValidationError({
                'produto_epi': 'O certificado deve pertencer a um produto de natureza EPI.'
            })

        numero_normalizado = cls.normalizar_numero(numero_ca)
        if not numero_normalizado:
            raise ValidationError({'numero_ca': 'Informe o número do CA.'})

        certificado = CertificadoEpi.objects.select_for_update().filter(
            numero_ca__iexact=numero_normalizado,
        ).first()
        if certificado and certificado.produto_epi_id != produto_epi.pk:
            raise ValidationError({
                'numero_ca': (
                    'Este CA já está associado a outro produto EPI. '
                    'Cadastre tamanhos como variantes do produto existente.'
                ),
            })

        if certificado is None:
            certificado = CertificadoEpi(
                produto_epi=produto_epi,
                numero_ca=numero_normalizado,
            )
        certificado.validade_ca = validade_ca
        certificado.observacao = (observacao or '').strip()
        certificado.ativo = ativo
        if snapshot_oficial is not None:
            certificado.situacao_oficial = (situacao_oficial or '').strip()
            certificado.snapshot_oficial = snapshot_oficial
            certificado.consultado_em = consultado_em
            certificado.importacao_caepi = importacao_caepi
        certificado.full_clean()
        certificado.save()
        return certificado
