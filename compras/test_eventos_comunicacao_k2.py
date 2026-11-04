import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from compras.models import (
    Aquisicao,
    EventoCompra,
    FornecedorEmpresa,
    ItemAquisicao,
    RemessaCompra,
)
from compras.services import AquisicaoService, RemessaCompraService
from estoque.models import Base, Comunicado, Empresa, Perfil
from insumos.models import CategoriaInsumo, FornecedorInsumo, Insumo


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    WHATSAPP_ENABLED=False,
)
class EventosComunicacaoComprasK2Tests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa eventos K2')
        self.outra_empresa = Empresa.objects.create(nome='Outro tenant eventos K2')
        self.base = Base.objects.create(nome='BASE EVENTOS K2', empresa=self.empresa)
        self.outra_base = Base.objects.create(
            nome='OUTRA BASE EVENTOS K2', empresa=self.outra_empresa,
        )
        self.admin = self._usuario('admin_eventos_k2', self.empresa)
        self.outro_admin = self._usuario('admin_outro_tenant_k2', self.outra_empresa)
        self.jose = self._usuario('jose.barboza', self.empresa)
        self.fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor eventos K2', documento='11222333000181',
        )
        FornecedorEmpresa.objects.create(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            cadastrado_por=self.admin,
            homologado_por=self.admin,
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria eventos K2')
        self.insumo = Insumo.objects.create(
            descricao='Insumo eventos K2', categoria=categoria,
            unidade_medida='UN',
        )

    @staticmethod
    def _usuario(username, empresa):
        usuario = User.objects.create_user(username, password='teste')
        Perfil.objects.update_or_create(
            user=usuario,
            defaults={'empresa': empresa, 'role': Perfil.Role.ADMIN},
        )
        usuario.refresh_from_db()
        return usuario

    def _criar_aquisicao(self):
        with self.captureOnCommitCallbacks(execute=True):
            return AquisicaoService.criar(
                empresa=self.empresa,
                fornecedor=self.fornecedor,
                usuario=self.admin,
                numero_documento='NF-K2-001',
                itens=[{
                    'tipo_item': ItemAquisicao.Tipo.INSUMO,
                    'insumo': self.insumo,
                    'quantidade': Decimal('10'),
                    'valor_unitario': Decimal('37.89'),
                }],
            )

    def test_aquisicao_emite_evento_estavel_sem_preco_e_sem_outro_tenant(self):
        aquisicao = self._criar_aquisicao()
        with self.captureOnCommitCallbacks(execute=True):
            AquisicaoService.aprovar(aquisicao, self.admin)

        self.assertEqual(
            list(aquisicao.eventos.values_list('tipo', flat=True)),
            ['AQUISICAO_CRIADA', 'AQUISICAO_APROVADA'],
        )
        comunicados = Comunicado.objects.filter(
            dados__aquisicao_id=aquisicao.pk,
        ).order_by('pk')
        self.assertEqual(
            list(comunicados.values_list('dados__evento', flat=True)),
            ['AQUISICAO_CRIADA', 'AQUISICAO_APROVADA'],
        )
        for comunicado in comunicados:
            conteudo = f'{comunicado.titulo} {comunicado.mensagem}'.lower()
            self.assertNotIn('37.89', conteudo)
            self.assertNotIn('r$', conteudo)
            self.assertNotIn('valor unit', conteudo)
            self.assertTrue(comunicado.usuarios.filter(pk=self.jose.pk).exists())
            self.assertFalse(
                comunicado.usuarios.filter(pk=self.outro_admin.pk).exists()
            )

    def test_confirmacao_idempotente_emite_um_evento_e_um_comunicado(self):
        aquisicao = self._criar_aquisicao()
        with self.captureOnCommitCallbacks(execute=True):
            AquisicaoService.aprovar(aquisicao, self.admin)
            remessa = RemessaCompraService.criar(
                empresa=self.empresa,
                fluxo=RemessaCompra.Fluxo.FORNECEDOR_DIRETO,
                aquisicao=aquisicao,
                base_destino=self.base,
                usuario=self.admin,
                itens=[{
                    'item_aquisicao': aquisicao.itens.get(),
                    'insumo': self.insumo,
                    'quantidade_prevista': Decimal('10'),
                    'custo_unitario_snapshot': Decimal('37.89'),
                }],
            )
            RemessaCompraService.enviar(remessa, self.admin)

        chave = uuid.uuid4()
        linhas = [{
            'item_id': remessa.itens.get().pk,
            'quantidade_recebida': Decimal('10'),
            'quantidade_avariada': Decimal('0'),
            'quantidade_faltante': Decimal('0'),
        }]
        with self.captureOnCommitCallbacks(execute=True):
            primeiro = RemessaCompraService.confirmar(
                remessa=remessa,
                usuario=self.admin,
                idempotency_key=chave,
                linhas=linhas,
                finalizar=True,
            )
            segundo = RemessaCompraService.confirmar(
                remessa=remessa,
                usuario=self.admin,
                idempotency_key=chave,
                linhas=linhas,
                finalizar=True,
            )

        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(
            EventoCompra.objects.filter(
                remessa=remessa,
                tipo='REMESSA_CONFERIDA',
            ).count(),
            1,
        )
        comunicados = Comunicado.objects.filter(
            dados__remessa_id=remessa.pk,
            dados__evento='REMESSA_CONFERIDA',
        )
        self.assertEqual(comunicados.count(), 1)
        self.assertNotIn('37.89', comunicados.get().mensagem)

    def test_transacao_revertida_nao_emite_evento_nem_comunicado(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValidationError):
                AquisicaoService.criar(
                    empresa=self.empresa,
                    fornecedor=self.fornecedor,
                    usuario=self.admin,
                    itens=[{
                        'tipo_item': ItemAquisicao.Tipo.INSUMO,
                        'insumo': self.insumo,
                        'quantidade': Decimal('0'),
                        'valor_unitario': Decimal('37.89'),
                    }],
                )

        self.assertFalse(Aquisicao.objects.exists())
        self.assertFalse(EventoCompra.objects.exists())
        self.assertFalse(Comunicado.objects.exists())
