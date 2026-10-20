from django.utils import timezone

from insumos.models import Insumo, ProdutoEpi
from insumos.services.alerta_epi_service import AlertaEpiService


class ChecklistEpiMetadataService:
    VERSAO_SCHEMA = 1

    @staticmethod
    def _estado_dict(estado):
        return {
            'codigo': estado.codigo,
            'dias_restantes': estado.dias_restantes,
            'faixa_dias': estado.faixa_dias,
        }
    @classmethod
    def resolver(cls, *, base, insumo, referencia=None):
        """Resolve um snapshot tenant-safe sem exigir escolhas extras no Checklist."""
        if not base or not insumo or insumo.natureza != Insumo.Natureza.EPI:
            return {}

        referencia = referencia or timezone.localdate()
        produto = ProdutoEpi.objects.filter(
            insumo=insumo,
            ativo=True,
        ).first()
        if produto is None:
            return {
                'schema': cls.VERSAO_SCHEMA,
                'natureza': Insumo.Natureza.EPI,
                'base_id': base.pk,
                'produto_configurado': False,
                'certificados': [],
                'lotes': [],
                'estado_ca': cls._estado_dict(
                    AlertaEpiService.estado_ca(
                        produto_epi=None,
                        referencia=referencia,
                    )
                ),
                'resolvido_em': timezone.now().isoformat(),
            }

        certificados = []
        for certificado in produto.certificados.filter(ativo=True).order_by(
            'numero_ca', 'pk',
        ):
            certificados.append({
                'id': certificado.pk,
                'numero_ca': certificado.numero_ca,
                'validade_ca': (
                    certificado.validade_ca.isoformat()
                    if certificado.validade_ca else None
                ),
                'estado': cls._estado_dict(
                    AlertaEpiService.estado_certificado(
                        certificado=certificado,
                        referencia=referencia,
                    )
                ),
            })

        lotes = []
        queryset_lotes = produto.lotes.filter(
            base=base,
            ativo=True,
        ).select_related('variante', 'certificado').order_by(
            'validade_fisica', 'codigo_lote', 'pk',
        )
        for lote in queryset_lotes:
            lotes.append({
                'id': lote.pk,
                'codigo_lote': lote.codigo_lote,
                'tamanho_variante': (
                    lote.variante.tamanho or lote.variante.nome
                    if lote.variante_id else None
                ),
                'numero_ca': (
                    lote.certificado.numero_ca if lote.certificado_id else None
                ),
                'fabricado_em': (
                    lote.fabricado_em.isoformat() if lote.fabricado_em else None
                ),
                'validade_fisica': (
                    lote.validade_fisica.isoformat()
                    if lote.validade_fisica else None
                ),
                'estado_ca': cls._estado_dict(
                    AlertaEpiService.estado_ca(
                        lote=lote,
                        referencia=referencia,
                    )
                ),
                'estado_validade_fisica': cls._estado_dict(
                    AlertaEpiService.estado_validade_fisica(
                        lote=lote,
                        referencia=referencia,
                    )
                ),
            })

        return {
            'schema': cls.VERSAO_SCHEMA,
            'natureza': Insumo.Natureza.EPI,
            'base_id': base.pk,
            'produto_configurado': True,
            'produto_epi_id': produto.pk,
            'fabricante_importador': produto.fabricante_importador,
            'certificados': certificados,
            'lotes': lotes,
            'estado_ca': cls._estado_dict(
                AlertaEpiService.estado_ca(
                    produto_epi=produto,
                    referencia=referencia,
                )
            ),
            'resolvido_em': timezone.now().isoformat(),
        }

