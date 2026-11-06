from decimal import Decimal
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from compras.forms import IndividualizacaoEquipamentoForm
from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
    EventoCompra,
    FornecedorEmpresa,
    ItemAquisicao,
    RemessaCompra,
    VinculoEquipamentoAquisicao,
)
from compras.services import (
    AquisicaoService,
    IndividualizacaoRecebimentoService,
    RemessaCompraService,
)
from estoque.models import Base, Empresa, Equipamento, Perfil, Produto
from insumos.models import FornecedorInsumo


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IndividualizacaoPosNFeR7GTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa R7G')
        self.base = Base.objects.create(nome='Base R7G', empresa=self.empresa)
        self.admin = self._usuario('admin.r7g', self.empresa, Perfil.Role.ADMIN)
        self.jose = self._usuario('jose.barboza', self.empresa, Perfil.Role.ADMIN)
        self.outra_empresa = Empresa.objects.create(nome='Empresa externa R7G')
        self.outro_admin = self._usuario(
            'admin.externo.r7g', self.outra_empresa, Perfil.Role.ADMIN,
        )
        self.fornecedor = FornecedorInsumo.objects.create(
            nome='Fornecedor R7G', documento='99887766000155',
        )
        FornecedorEmpresa.objects.create(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            cadastrado_por=self.admin,
            homologado_por=self.admin,
        )
        self.produto = Produto.objects.create(
            codigo='CEL-R7G', descricao='Celular R7G', fabricante='Marca',
            modelo='Modelo R7G', categoria='Celulares',
        )
        catalogo = CatalogoProdutoEmpresa.objects.create(
            empresa=self.empresa,
            produto=self.produto,
            configurado_por=self.admin,
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_IMEI,
            configurado_por=self.admin,
        )
        aquisicao = AquisicaoService.criar(
            empresa=self.empresa,
            fornecedor=self.fornecedor,
            usuario=self.admin,
            numero_documento='NF-R7G-10',
            itens=[{
                'tipo_item': ItemAquisicao.Tipo.EQUIPAMENTO,
                'produto': self.produto,
                'quantidade': 2,
                'valor_unitario': Decimal('1500'),
            }],
        )
        AquisicaoService.aprovar(aquisicao, self.admin)
        self.remessa = RemessaCompraService.criar(
            empresa=self.empresa,
            fluxo=RemessaCompra.Fluxo.FORNECEDOR_DIRETO,
            aquisicao=aquisicao,
            base_destino=self.base,
            usuario=self.admin,
            itens=[{
                'item_aquisicao': aquisicao.itens.get(),
                'produto': self.produto,
                'quantidade_prevista': 2,
                'custo_unitario_snapshot': Decimal('1500'),
            }],
        )
        RemessaCompraService.enviar(self.remessa, self.admin)
        self.item = self.remessa.itens.get()
        RemessaCompraService.confirmar(
            remessa=self.remessa,
            usuario=self.admin,
            idempotency_key=uuid.uuid4(),
            linhas=[{'item_id': self.item.pk, 'quantidade_recebida': 2}],
            finalizar=True,
        )
        self.item.refresh_from_db()

    @staticmethod
    def _usuario(username, empresa, role):
        usuario = User.objects.create_user(username, password='Teste123!')
        usuario.perfil.empresa = empresa
        usuario.perfil.role = role
        usuario.perfil.save()
        return usuario

    def _dados(self, *, serie, patrimonio, imei_1=''):
        return {
            'numero_serie': serie,
            'patrimonio': patrimonio,
            'imei_1': imei_1,
            'imei_2': '',
            'finalidade': Equipamento.Finalidade.OPERACIONAL,
            'responsavel': '',
            'observacao_operacional': 'Recebido e conferido',
        }

    def _form_valido(self, **dados):
        form = IndividualizacaoEquipamentoForm(
            data=self._dados(**dados),
            item_remessa=self.item,
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_jose_nao_acessa_identificacao_de_recebimentos(self):
        self.client.force_login(self.jose)
        fila = self.client.get(reverse('compras:individualizacao_pendentes'))
        self.assertEqual(fila.status_code, 403)
        url = reverse(
            'compras:remessa_individualizar_item',
            args=[self.remessa.pk, self.item.pk],
        )
        tela = self.client.get(url)
        self.assertEqual(tela.status_code, 403)

    def test_limite_fisico_e_evento_auditavel(self):
        for indice in (1, 2):
            form = self._form_valido(
                serie=f'SERIE-LIMITE-{indice}',
                patrimonio=f'PAT-LIMITE-{indice}',
            )
            IndividualizacaoRecebimentoService.criar_unidade(
                item_remessa=self.item,
                usuario=self.admin,
                dados=form.cleaned_data,
            )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade_pendente_individualizacao, Decimal('0'))
        self.assertEqual(self.item.equipamentos_individualizados.count(), 2)
        self.assertEqual(EventoCompra.objects.filter(
            remessa=self.remessa,
            tipo='EQUIPAMENTO_INDIVIDUALIZADO',
        ).count(), 2)

        with self.assertRaises(ValidationError):
            IndividualizacaoRecebimentoService.criar_unidade(
                item_remessa=self.item,
                usuario=self.admin,
                dados=self._dados(
                    serie='SERIE-EXCEDENTE', patrimonio='PAT-EXCEDENTE',
                ),
            )
        self.assertFalse(Equipamento.objects.filter(
            numero_serie='SERIE-EXCEDENTE',
        ).exists())

    def test_imei_continua_opcional_mas_valida_quando_informado(self):
        sem_imei = self._form_valido(serie='SERIE-SEM-IMEI', patrimonio='PAT-SEM-IMEI')
        self.assertIsNone(sem_imei.cleaned_data['imei_1'])

        invalido = IndividualizacaoEquipamentoForm(
            data=self._dados(
                serie='SERIE-IMEI-RUIM',
                patrimonio='PAT-IMEI-RUIM',
                imei_1='1234',
            ),
            item_remessa=self.item,
        )
        self.assertFalse(invalido.is_valid())
        self.assertIn('imei_1', invalido.errors)

    def test_admin_de_outra_empresa_nao_descobre_nem_individualiza_item(self):
        self.client.force_login(self.outro_admin)
        url = reverse(
            'compras:remessa_individualizar_item',
            args=[self.remessa.pk, self.item.pk],
        )
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(url, self._dados(
                serie='SERIE-EXTERNA', patrimonio='PAT-EXTERNO',
            )).status_code,
            404,
        )
        self.assertFalse(Equipamento.objects.filter(
            numero_serie='SERIE-EXTERNA',
        ).exists())
